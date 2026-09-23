-- 개인화 Dimension, 일별 사용량 Fact, Feature Snapshot을 생성한다.
insert into dm_personalization.dim_plan
select plan_id,plan_name,monthly_fee,data_limit_gb,is_unlimited from dw_common.plan
on conflict(plan_id)
    do update set (plan_name,monthly_fee,data_limit_gb,is_unlimited)=
(excluded.plan_name,excluded.monthly_fee,excluded.data_limit_gb,excluded.is_unlimited);

insert into dm_personalization.dim_content(content_category,content_detail)
select distinct content_category,content_detail
    from dw_personalization.content_usage
    where source_batch_id=:'batch_id'::uuid
    on conflict do nothing;

with bounds as (select min(usage_date) lo,
    max(usage_date) hi from landing.raw_content_usage where source_batch_id=:'batch_id'::uuid),
dates as (select d::date calendar_date from bounds cross join lateral generate_series(lo,hi,
    interval '1 day') d)
insert into dm_personalization.dim_date
select to_char(calendar_date,'YYYYMMDD')::int,calendar_date,date_trunc('month',calendar_date)::date,
extract(year from calendar_date)::int,extract(quarter from calendar_date)::int,
    extract(isodow from calendar_date)::int,
extract(isodow from calendar_date) in (6,7)
    from dates on conflict(calendar_date) do nothing;

-- 개인화 팩트의 입도: 사용자 × 사용 일자 × 콘텐츠 대/상세분류.
insert into dm_personalization.dim_customer(source_batch_id,user_id,current_plan_id,age,gender,
    subscription_start_date)
select source_batch_id,user_id,current_plan_id,age,gender,subscription_start_date
from dw_personalization.customer_profile where source_batch_id=:'batch_id'::uuid;

insert into dm_personalization.fact_customer_daily_usage
select x.source_batch_id,dc.customer_key,x.usage_date,dc.current_plan_id,k.content_key,x.data_usage_mb,
       x.daily_total_usage_mb,x.month_to_date_usage_mb,
       case when p.is_unlimited or p.data_limit_gb is null or p.data_limit_gb=0 then null
            else x.month_to_date_usage_mb/(p.data_limit_gb*1024) end
from (
  select c.*,sum(data_usage_mb) over(partition by source_batch_id,user_id,usage_date) daily_total_usage_mb,
         sum(data_usage_mb) over(partition by source_batch_id,user_id,date_trunc('month',
             usage_date) order by usage_date) month_to_date_usage_mb
  from dw_personalization.content_usage c where source_batch_id=:'batch_id'::uuid
) x
join dm_personalization.dim_customer dc on (dc.source_batch_id,dc.user_id)=(x.source_batch_id,x.user_id)
join dm_personalization.dim_content k on (k.content_category,k.content_detail)=(x.content_category,
    x.content_detail)
join dm_personalization.dim_plan p on p.plan_id=dc.current_plan_id;

-- 특성 테이블의 입도: 원천 배치 × user_id × 특성 기준일.
with daily as (
  select source_batch_id,user_id,usage_date,sum(data_usage_mb) usage_mb
  from dw_personalization.content_usage
      where source_batch_id=:'batch_id'::uuid
      group by 1,2,3
), dates as (select distinct usage_date from daily), base as (
  select cp.source_batch_id,cp.user_id,d.usage_date
      from dw_personalization.customer_profile cp
      cross join dates d
  where cp.source_batch_id=:'batch_id'::uuid
), metrics as (
  select b.source_batch_id,b.user_id,b.usage_date,
         coalesce(sum(d.usage_mb) filter(where d.usage_date between b.usage_date-6 and b.usage_date),
             0) trailing_7d_usage_mb,
         coalesce(sum(d.usage_mb) filter(where d.usage_date between b.usage_date-29 and b.usage_date),
             0) trailing_30d_usage_mb,
         coalesce(sum(d.usage_mb) filter(where date_trunc('month',d.usage_date)=date_trunc('month',
             b.usage_date)),0) month_to_date_usage_mb
  from base b
      left join daily d on d.source_batch_id=b.source_batch_id
          and d.user_id=b.user_id
          and d.usage_date between b.usage_date-29 and b.usage_date
  group by 1,2,3
), category_usage as (
  select b.source_batch_id,b.user_id,b.usage_date,c.content_category,sum(c.data_usage_mb) usage_mb
  from base b
      left join dw_personalization.content_usage c on c.source_batch_id=b.source_batch_id
          and c.user_id=b.user_id
          and c.usage_date between b.usage_date-29 and b.usage_date
  group by 1,2,3,4
), category_ratio as (
  select *,usage_mb/nullif(sum(usage_mb) over(partition by source_batch_id,user_id,usage_date),0) ratio
      from category_usage
      where content_category is not null
), category_features as (
  select source_batch_id,user_id,usage_date,jsonb_object_agg(content_category,round(ratio,8)) ratios,
         (array_agg(content_category order by usage_mb desc,content_category))[1] preferred_content_category
  from category_ratio group by 1,2,3
)
insert into dm_personalization.customer_usage_feature_snapshot
select m.source_batch_id,m.user_id,m.usage_date,m.trailing_7d_usage_mb,m.trailing_30d_usage_mb,
       coalesce(f.ratios,'{}'::jsonb),f.preferred_content_category,m.month_to_date_usage_mb,
       case when p.is_unlimited or p.data_limit_gb is null or p.data_limit_gb=0 then null
            else m.month_to_date_usage_mb/(p.data_limit_gb*1024) end
from metrics m
    join dw_personalization.customer_profile cp on (cp.source_batch_id,
    cp.user_id)=(m.source_batch_id,m.user_id)
join dm_personalization.dim_plan p on p.plan_id=cp.current_plan_id
left join category_features f on (f.source_batch_id,f.user_id,f.usage_date)=(m.source_batch_id,
    m.user_id,m.usage_date);
