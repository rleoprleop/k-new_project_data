insert into dm_personalization.dim_content(content_category,content_detail)
select distinct content_category,content_detail
from dw_personalization.content_usage
where usage_date between current_setting('pipeline.event_date_from')::date
    and current_setting('pipeline.event_date_to')::date
on conflict do nothing;

insert into dm_personalization.dim_date
select to_char(d,'YYYYMMDD')::int,d,date_trunc('month',d)::date,
    extract(year from d)::int,extract(quarter from d)::int,
    extract(isodow from d)::int,extract(isodow from d) in (6,7)
from incremental_context c
cross join lateral generate_series(c.event_date_from,c.feature_rebuild_to,interval '1 day') x(d)
on conflict(calendar_date) do nothing;

delete from dm_personalization.fact_customer_daily_usage f
using incremental_context c
where f.usage_date between c.event_date_from and c.fact_rebuild_to;

with usage_window as (
  select u.*,
      sum(data_usage_mb) over(partition by user_id,usage_date) daily_total_usage_mb,
      sum(data_usage_mb) over(
          partition by user_id,date_trunc('month',usage_date)
          order by usage_date
          range between unbounded preceding and current row) month_to_date_usage_mb
  from dw_personalization.content_usage u
  cross join incremental_context c
  where u.usage_date between date_trunc('month',c.event_date_from)::date
      and c.fact_rebuild_to
), target as (
  select u.* from usage_window u cross join incremental_context c
  where u.usage_date between c.event_date_from and c.fact_rebuild_to
)
insert into dm_personalization.fact_customer_daily_usage(
    source_batch_id,customer_key,usage_date,plan_id,content_key,data_usage_mb,
    daily_total_usage_mb,month_to_date_usage_mb,quota_utilization)
select current_setting('pipeline.batch_id')::uuid,dc.customer_key,x.usage_date,
    dc.current_plan_id,k.content_key,x.data_usage_mb,x.daily_total_usage_mb,
    x.month_to_date_usage_mb,
    case when p.is_unlimited or p.data_limit_gb is null or p.data_limit_gb=0 then null
         else x.month_to_date_usage_mb/(p.data_limit_gb*1024) end
from target x
join dm_personalization.dim_customer dc on dc.user_id=x.user_id
join dm_personalization.dim_content k
  on (k.content_category,k.content_detail)=(x.content_category,x.content_detail)
join dm_personalization.dim_plan p on p.plan_id=dc.current_plan_id;

delete from dm_personalization.customer_usage_feature_snapshot f
using incremental_context c
where f.feature_reference_date between c.event_date_from and c.feature_rebuild_to;

with target_dates as (
  select d::date feature_reference_date
  from incremental_context c
  cross join lateral generate_series(c.event_date_from,c.feature_rebuild_to,interval '1 day') x(d)
), daily as (
  select user_id,usage_date,sum(data_usage_mb) usage_mb
  from dw_personalization.content_usage u
  cross join incremental_context c
  where u.usage_date between least(c.event_date_from-29,
      date_trunc('month',c.event_date_from)::date) and c.feature_rebuild_to
  group by user_id,usage_date
), base as (
  select cp.user_id,d.feature_reference_date
  from dw_personalization.customer_profile cp cross join target_dates d
), metrics as (
  select b.user_id,b.feature_reference_date,
      coalesce(sum(d.usage_mb) filter(where d.usage_date between
          b.feature_reference_date-6 and b.feature_reference_date),0) trailing_7d_usage_mb,
      coalesce(sum(d.usage_mb) filter(where d.usage_date between
          b.feature_reference_date-29 and b.feature_reference_date),0) trailing_30d_usage_mb,
      coalesce(sum(d.usage_mb) filter(where date_trunc('month',d.usage_date)=
          date_trunc('month',b.feature_reference_date)),0) month_to_date_usage_mb
  from base b
  left join daily d on d.user_id=b.user_id
      and d.usage_date between least(b.feature_reference_date-29,
          date_trunc('month',b.feature_reference_date)::date) and b.feature_reference_date
  group by b.user_id,b.feature_reference_date
), category_usage as (
  select b.user_id,b.feature_reference_date,u.content_category,sum(u.data_usage_mb) usage_mb
  from base b
  left join dw_personalization.content_usage u on u.user_id=b.user_id
      and u.usage_date between b.feature_reference_date-29 and b.feature_reference_date
  group by b.user_id,b.feature_reference_date,u.content_category
), category_ratio as (
  select *,usage_mb/nullif(sum(usage_mb) over(
      partition by user_id,feature_reference_date),0) ratio
  from category_usage where content_category is not null
), category_features as (
  select user_id,feature_reference_date,
      jsonb_object_agg(content_category,round(ratio,8)) ratios,
      (array_agg(content_category order by usage_mb desc,content_category))[1]
          preferred_content_category
  from category_ratio group by user_id,feature_reference_date
)
insert into dm_personalization.customer_usage_feature_snapshot(
    source_batch_id,user_id,feature_reference_date,trailing_7d_usage_mb,
    trailing_30d_usage_mb,content_category_usage_ratio,preferred_content_category,
    month_to_date_usage_mb,plan_quota_utilization)
select current_setting('pipeline.batch_id')::uuid,m.user_id,m.feature_reference_date,
    m.trailing_7d_usage_mb,m.trailing_30d_usage_mb,coalesce(f.ratios,'{}'::jsonb),
    f.preferred_content_category,m.month_to_date_usage_mb,
    case when p.is_unlimited or p.data_limit_gb is null or p.data_limit_gb=0 then null
         else m.month_to_date_usage_mb/(p.data_limit_gb*1024) end
from metrics m
join dw_personalization.customer_profile cp on cp.user_id=m.user_id
join dm_personalization.dim_plan p on p.plan_id=cp.current_plan_id
left join category_features f
  on (f.user_id,f.feature_reference_date)=(m.user_id,m.feature_reference_date);
