insert into dm_personalization.dim_content(content_category,content_detail)
select distinct content_category,content_detail
from dw_personalization.content_usage u cross join incremental_context c
where u.usage_date between c.event_date_from and c.event_date_to on conflict do nothing;

insert into dm_personalization.dim_date
select to_char(d,'YYYYMMDD')::integer,d,date_trunc('month',d)::date,
  extract(year from d)::integer,extract(quarter from d)::integer,
  extract(day from d)::integer,extract(isodow from d)::integer,extract(isodow from d) in (6,7)
from incremental_context c
cross join lateral generate_series(date_trunc('month',c.event_date_from)::date,
  c.fact_rebuild_to,interval '1 day') x(d)
on conflict(calendar_date) do nothing;

insert into dm_personalization.bridge_service_content(service_id,content_key)
select m.service_id,c.content_key from (values
  ('S001','netflix'),('S002','youtube_video'),('S002','youtube_shorts'),('S002','youtube_music'),
  ('S003','tving'),('S004','genie_music'),('S005','milli_ebook'),
  ('S006','disney_plus'),('S009','google_ai')) m(service_id,content_detail)
join dm_personalization.dim_service s on s.service_id=m.service_id
join dm_personalization.dim_content c on c.content_detail=m.content_detail on conflict do nothing;

delete from dm_personalization.customer_daily_usage f using incremental_context c
where f.date_key between to_char(c.event_date_from,'YYYYMMDD')::integer
  and to_char(c.fact_rebuild_to,'YYYYMMDD')::integer;

with daily as (
  select u.source_batch_id,u.user_id,u.usage_date,sum(u.data_usage_mb) total_usage_mb
  from dw_personalization.content_usage u cross join incremental_context c
  where u.usage_date between date_trunc('month',c.event_date_from)::date and c.fact_rebuild_to
  group by 1,2,3
), calculated as (
  select daily.*,sum(total_usage_mb) over(partition by user_id,date_trunc('month',usage_date)
    order by usage_date rows between unbounded preceding and current row) month_to_date_usage_mb
  from daily
)
insert into dm_personalization.customer_daily_usage
select current_setting('pipeline.batch_id')::uuid,u.customer_key,d.date_key,
  x.total_usage_mb,x.month_to_date_usage_mb
from calculated x
join dm_personalization.dim_customer u on u.user_id=x.user_id
join dm_personalization.dim_date d on d.calendar_date=x.usage_date
cross join incremental_context c
where x.usage_date between c.event_date_from and c.fact_rebuild_to;

delete from dm_personalization.customer_monthly_usage f using incremental_context c
where f.month_key between to_char(date_trunc('month',c.event_date_from),'YYYYMMDD')::integer
  and to_char(date_trunc('month',c.fact_rebuild_to),'YYYYMMDD')::integer;
delete from dm_personalization.customer_monthly_content_usage f using incremental_context c
where f.month_key between to_char(date_trunc('month',c.event_date_from),'YYYYMMDD')::integer
  and to_char(date_trunc('month',c.fact_rebuild_to),'YYYYMMDD')::integer;

insert into dm_personalization.customer_monthly_usage
select current_setting('pipeline.batch_id')::uuid,u.customer_key,
  to_char(d.calendar_month,'YYYYMMDD')::integer,sum(x.data_usage_mb),
  sum(x.data_usage_mb)/count(distinct x.usage_date)
from dw_personalization.content_usage x
join dm_personalization.dim_customer u on u.user_id=x.user_id
join dm_personalization.dim_date d on d.calendar_date=x.usage_date
cross join incremental_context c
where x.usage_date between date_trunc('month',c.event_date_from)::date and c.fact_rebuild_to
group by u.customer_key,d.calendar_month;

insert into dm_personalization.customer_monthly_content_usage
select current_setting('pipeline.batch_id')::uuid,u.customer_key,
  to_char(d.calendar_month,'YYYYMMDD')::integer,k.content_key,sum(x.data_usage_mb)
from dw_personalization.content_usage x
join dm_personalization.dim_customer u on u.user_id=x.user_id
join dm_personalization.dim_date d on d.calendar_date=x.usage_date
join dm_personalization.dim_content k
  on (k.content_category,k.content_detail)=(x.content_category,x.content_detail)
cross join incremental_context c
where x.usage_date between date_trunc('month',c.event_date_from)::date and c.fact_rebuild_to
group by u.customer_key,d.calendar_month,k.content_key;
