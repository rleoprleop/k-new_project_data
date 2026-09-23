-- 운영 Dimension과 일별 사용량 Fact를 생성한다.
insert into dm_operations.dim_plan
select plan_id,plan_name,plan_family,plan_category,monthly_fee,data_limit_gb,is_unlimited
    from dw_common.plan
on conflict(plan_id)
    do update set (plan_name,plan_family,plan_category,monthly_fee,data_limit_gb,is_unlimited)=
(excluded.plan_name,excluded.plan_family,excluded.plan_category,excluded.monthly_fee,
    excluded.data_limit_gb,excluded.is_unlimited);

insert into dm_operations.dim_content(content_category,content_detail)
select distinct content_category,content_detail
    from dw_operations.content_usage
    where source_batch_id=:'batch_id'::uuid
    on conflict do nothing;

insert into dm_operations.dim_age_band(age_band_key,age_band,min_age,max_age) values
(1,'8-12',8,12),(2,'13-18',13,18),(3,'19-24',19,24),(4,'25-34',25,34),
(5,'35-49',35,49),(6,'50-64',50,64),(7,'65+',65,null)
    on conflict(age_band_key) do nothing;
with bounds as (select min(usage_date) lo,
    max(usage_date) hi from landing.raw_content_usage where source_batch_id=:'batch_id'::uuid),
dates as (select d::date calendar_date from bounds cross join lateral generate_series(lo,hi,
    interval '1 day') d)
insert into dm_operations.dim_date
select to_char(calendar_date,'YYYYMMDD')::int,calendar_date,date_trunc('month',calendar_date)::date,
extract(year from calendar_date)::int,extract(quarter from calendar_date)::int,
    extract(isodow from calendar_date)::int,
extract(isodow from calendar_date) in (6,7)
    from dates on conflict(calendar_date) do nothing;

-- 운영 팩트의 입도: 사용 일자 × 현재 요금제 × 연령 구간 × 콘텐츠 대/상세분류.
insert into dm_operations.fact_daily_usage_summary
select c.source_batch_id,c.usage_date,u.current_plan_id,a.age_band_key,k.content_key,
       sum(c.data_usage_mb),count(distinct c.analysis_user_key),
       sum(c.data_usage_mb)/nullif(count(distinct c.analysis_user_key),0),count(*)
from dw_operations.content_usage c
join dw_operations.customer u on (u.source_batch_id,u.analysis_user_key)=(c.source_batch_id,
    c.analysis_user_key)
join dm_operations.dim_age_band a on a.age_band=u.age_band
join dm_operations.dim_content k on (k.content_category,k.content_detail)=(c.content_category,
    c.content_detail)
where c.source_batch_id=:'batch_id'::uuid
group by c.source_batch_id,c.usage_date,u.current_plan_id,a.age_band_key,k.content_key;
