insert into dm_operations.dim_content(content_category,content_detail)
select distinct content_category,content_detail
from dw_operations.content_usage
where usage_date between current_setting('pipeline.event_date_from')::date
    and current_setting('pipeline.event_date_to')::date
on conflict do nothing;

insert into dm_operations.dim_date
select to_char(d,'YYYYMMDD')::int,d,date_trunc('month',d)::date,
    extract(year from d)::int,extract(quarter from d)::int,
    extract(isodow from d)::int,extract(isodow from d) in (6,7)
from generate_series(
    current_setting('pipeline.event_date_from')::date,
    current_setting('pipeline.event_date_to')::date,
    interval '1 day') x(d)
on conflict(calendar_date) do nothing;

delete from dm_operations.fact_daily_usage_summary
where usage_date between current_setting('pipeline.event_date_from')::date
    and current_setting('pipeline.event_date_to')::date;

insert into dm_operations.fact_daily_usage_summary(
    source_batch_id,usage_date,plan_id,age_band_key,content_key,total_usage_mb,
    active_user_count,average_usage_mb,usage_event_count)
select current_setting('pipeline.batch_id')::uuid,c.usage_date,u.current_plan_id,a.age_band_key,
    k.content_key,sum(c.data_usage_mb),count(distinct c.analysis_user_key),
    sum(c.data_usage_mb)/nullif(count(distinct c.analysis_user_key),0),count(*)
from dw_operations.content_usage c
join dw_operations.customer u on u.analysis_user_key=c.analysis_user_key
join dm_operations.dim_age_band a on a.age_band=u.age_band
join dm_operations.dim_content k
  on (k.content_category,k.content_detail)=(c.content_category,c.content_detail)
where c.usage_date between current_setting('pipeline.event_date_from')::date
    and current_setting('pipeline.event_date_to')::date
group by c.usage_date,u.current_plan_id,a.age_band_key,k.content_key;
