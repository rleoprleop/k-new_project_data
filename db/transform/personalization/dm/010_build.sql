insert into dm_personalization.dim_date
select to_char(d,'YYYYMMDD')::integer,d,date_trunc('month',d)::date,
  extract(year from d)::integer,extract(quarter from d)::integer,
  extract(day from d)::integer,extract(isodow from d)::integer,
  extract(isodow from d) in (6,7)
from generate_series((select date_trunc('month',min(usage_date))::date from dw_personalization.content_usage),
  (select max(usage_date) from dw_personalization.content_usage),interval '1 day') x(d);

insert into dm_personalization.dim_plan
select plan_id,plan_name,plan_family,plan_category,monthly_fee,data_limit_gb,is_unlimited,
  choice_tier,network_type from dw_personalization.plans;
insert into dm_personalization.dim_content(content_category,content_detail)
select distinct content_category,content_detail
from dw_personalization.content_usage order by 1,2;
insert into dm_personalization.dim_service
select service_id,service_name,service_category,normal_monthly_price
from dw_personalization.additional_services;
insert into dm_personalization.dim_discount
select discount_id,policy_domain,benefit_code,discount_name from dw_personalization.discounts;
insert into dm_personalization.dim_family(
  family_id,has_bundle,bundle_type,has_kt_internet,internet_product_group,internet_status)
select family_id,has_bundle,bundle_type,has_kt_internet,internet_product_group,internet_status
from dw_personalization.families;

insert into dm_personalization.dim_customer(
  source_batch_id,user_id,name,plan_id,age,gender,subscription_start_date,family_key)
select u.source_batch_id,u.user_id,u.name,u.current_plan_id,u.age,u.gender,
  u.subscription_start_date,f.family_key
from dw_personalization.users u
left join dm_personalization.dim_family f on f.family_id=u.family_id;

insert into dm_personalization.bridge_service_content(service_id,content_key)
select m.service_id,c.content_key
from (values
  ('S001','netflix'),('S002','youtube_video'),('S002','youtube_shorts'),
  ('S002','youtube_music'),('S003','tving'),('S004','genie_music'),
  ('S005','milli_ebook'),('S006','disney_plus'),('S009','google_ai')
) m(service_id,content_detail)
join dm_personalization.dim_service s on s.service_id=m.service_id
join dm_personalization.dim_content c on c.content_detail=m.content_detail;

with daily as (
  select source_batch_id,user_id,usage_date,sum(data_usage_mb) total_usage_mb
  from dw_personalization.content_usage group by 1,2,3
), calculated as (
  select daily.*,
    sum(total_usage_mb) over(partition by user_id,date_trunc('month',usage_date)
      order by usage_date rows between unbounded preceding and current row) month_to_date_usage_mb
  from daily
)
insert into dm_personalization.customer_daily_usage
select x.source_batch_id,c.customer_key,d.date_key,x.total_usage_mb,x.month_to_date_usage_mb
from calculated x
join dm_personalization.dim_customer c on c.user_id=x.user_id
join dm_personalization.dim_date d on d.calendar_date=x.usage_date;

insert into dm_personalization.customer_monthly_usage
select :'batch_id'::uuid,c.customer_key,to_char(d.calendar_month,'YYYYMMDD')::integer,
  sum(u.data_usage_mb),sum(u.data_usage_mb)/count(distinct u.usage_date)
from dw_personalization.content_usage u
join dm_personalization.dim_customer c on c.user_id=u.user_id
join dm_personalization.dim_date d on d.calendar_date=u.usage_date
group by c.customer_key,d.calendar_month;

insert into dm_personalization.customer_monthly_content_usage
select :'batch_id'::uuid,c.customer_key,to_char(d.calendar_month,'YYYYMMDD')::integer,
  k.content_key,sum(u.data_usage_mb)
from dw_personalization.content_usage u
join dm_personalization.dim_customer c on c.user_id=u.user_id
join dm_personalization.dim_date d on d.calendar_date=u.usage_date
join dm_personalization.dim_content k
  on (k.content_category,k.content_detail)=(u.content_category,u.content_detail)
group by c.customer_key,d.calendar_month,k.content_key;

insert into dm_personalization.customer_service_current
select :'batch_id'::uuid,c.customer_key,s.service_id,s.benefit_type,s.start_date
from dw_personalization.user_services s
join dm_personalization.dim_customer c on c.user_id=s.user_id
where s.start_date<=:'reference_date'::date;

insert into dm_personalization.customer_discount_current
select distinct on(c.customer_key,d.discount_id)
  :'batch_id'::uuid,c.customer_key,d.discount_id,d.start_date
from dw_personalization.user_discounts d
join dm_personalization.dim_customer c on c.user_id=d.user_id
where d.status='ACTIVE' and d.start_date<=:'reference_date'::date
  and (d.end_date is null or d.end_date>=:'reference_date'::date)
order by c.customer_key,d.discount_id,d.start_date desc;

insert into dm_personalization.customer_family_current
select :'batch_id'::uuid,c.customer_key,c.family_key
from dm_personalization.dim_customer c where c.family_key is not null;
