insert into dm_operations.dim_content_category(content_category)
select distinct content_category from dw_operations.content_usage u cross join incremental_context c
where u.usage_date between c.event_date_from and c.event_date_to on conflict do nothing;

insert into dm_operations.dim_date
select to_char(d,'YYYYMMDD')::integer,d,date_trunc('month',d)::date,
  extract(year from d)::integer,extract(quarter from d)::integer,
  extract(day from d)::integer,extract(isodow from d)::integer,extract(isodow from d) in (6,7)
from incremental_context c
cross join lateral generate_series(date_trunc('month',c.event_date_from)::date,
  c.fact_rebuild_to,interval '1 day') x(d)
on conflict(calendar_date) do nothing;

delete from dm_operations.daily_usage_segment f using incremental_context c
where f.date_key between to_char(c.event_date_from,'YYYYMMDD')::integer
  and to_char(c.fact_rebuild_to,'YYYYMMDD')::integer;
delete from dm_operations.customer_daily_usage f using incremental_context c
where f.date_key between to_char(c.event_date_from,'YYYYMMDD')::integer
  and to_char(c.fact_rebuild_to,'YYYYMMDD')::integer;

insert into dm_operations.daily_usage_segment
select current_setting('pipeline.batch_id')::uuid,d.date_key,u.current_plan_id,a.age_band_key,
  k.category_key,sum(x.data_usage_mb),count(distinct x.analysis_user_key),
  sum(x.data_usage_mb)/nullif(count(distinct x.analysis_user_key),0)
from dw_operations.content_usage x
join dw_operations.users u on u.analysis_user_key=x.analysis_user_key
join dm_operations.dim_age_band a on a.age_band=u.age_band
join dm_operations.dim_date d on d.calendar_date=x.usage_date
join dm_operations.dim_content_category k on k.content_category=x.content_category
cross join incremental_context c
where x.usage_date between c.event_date_from and c.fact_rebuild_to
group by d.date_key,u.current_plan_id,a.age_band_key,k.category_key;

insert into dm_operations.customer_daily_usage
select current_setting('pipeline.batch_id')::uuid,u.customer_key,d.date_key,sum(x.data_usage_mb)
from dw_operations.content_usage x
join dm_operations.dim_analysis_customer u on u.analysis_user_key=x.analysis_user_key
join dm_operations.dim_date d on d.calendar_date=x.usage_date
cross join incremental_context c
where x.usage_date between c.event_date_from and c.fact_rebuild_to
group by u.customer_key,d.date_key;

delete from dm_operations.monthly_usage_segment f using incremental_context c
where f.month_key between to_char(date_trunc('month',c.event_date_from),'YYYYMMDD')::integer
  and to_char(date_trunc('month',c.fact_rebuild_to),'YYYYMMDD')::integer;
delete from dm_operations.customer_monthly_category_usage f using incremental_context c
where f.month_key between to_char(date_trunc('month',c.event_date_from),'YYYYMMDD')::integer
  and to_char(date_trunc('month',c.fact_rebuild_to),'YYYYMMDD')::integer;

insert into dm_operations.monthly_usage_segment
select current_setting('pipeline.batch_id')::uuid,to_char(d.calendar_month,'YYYYMMDD')::integer,
  u.current_plan_id,a.age_band_key,k.category_key,sum(x.data_usage_mb),
  count(distinct x.analysis_user_key),sum(x.data_usage_mb)/nullif(count(distinct x.analysis_user_key),0)
from dw_operations.content_usage x
join dw_operations.users u on u.analysis_user_key=x.analysis_user_key
join dm_operations.dim_age_band a on a.age_band=u.age_band
join dm_operations.dim_date d on d.calendar_date=x.usage_date
join dm_operations.dim_content_category k on k.content_category=x.content_category
cross join incremental_context c
where x.usage_date between date_trunc('month',c.event_date_from)::date and c.fact_rebuild_to
group by d.calendar_month,u.current_plan_id,a.age_band_key,k.category_key;

insert into dm_operations.customer_monthly_category_usage
select current_setting('pipeline.batch_id')::uuid,u.customer_key,
  to_char(d.calendar_month,'YYYYMMDD')::integer,k.category_key,sum(x.data_usage_mb)
from dw_operations.content_usage x
join dm_operations.dim_analysis_customer u on u.analysis_user_key=x.analysis_user_key
join dm_operations.dim_date d on d.calendar_date=x.usage_date
join dm_operations.dim_content_category k on k.content_category=x.content_category
cross join incremental_context c
where x.usage_date between date_trunc('month',c.event_date_from)::date and c.fact_rebuild_to
group by u.customer_key,d.calendar_month,k.category_key;
