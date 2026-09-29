insert into dm_operations.dim_age_band(age_band_key,age_band,min_age,max_age) values
(1,'8-12',8,12),(2,'13-18',13,18),(3,'19-24',19,24),(4,'25-34',25,34),
(5,'35-49',35,49),(6,'50-64',50,64),(7,'65+',65,null);

insert into dm_operations.dim_date
select to_char(d,'YYYYMMDD')::integer,d,date_trunc('month',d)::date,
  extract(year from d)::integer,extract(quarter from d)::integer,
  extract(day from d)::integer,extract(isodow from d)::integer,
  extract(isodow from d) in (6,7)
from generate_series((select date_trunc('month',min(usage_date))::date from dw_operations.content_usage),
  (select max(usage_date) from dw_operations.content_usage),interval '1 day') x(d);

insert into dm_operations.dim_plan
select plan_id,plan_name,plan_family,plan_category,monthly_fee,data_limit_gb,is_unlimited
from dw_operations.plans;
insert into dm_operations.dim_content_category(content_category)
select distinct content_category from dw_operations.content_usage order by 1;
insert into dm_operations.dim_service
select service_id,service_name,service_category,normal_monthly_price
from dw_operations.additional_services;
insert into dm_operations.dim_discount
select discount_id,policy_domain,benefit_code,discount_name from dw_operations.discounts;

insert into dm_operations.dim_analysis_family(
  analysis_family_key,has_bundle,bundle_type,has_kt_internet,internet_product_group,internet_status)
select analysis_family_key,has_bundle,bundle_type,has_kt_internet,internet_product_group,internet_status
from dw_operations.families;

insert into dm_operations.dim_analysis_customer(
  analysis_user_key,plan_id,age_band_key,gender,subscription_start_date,family_key)
select u.analysis_user_key,u.current_plan_id,a.age_band_key,u.gender,u.subscription_start_date,f.family_key
from dw_operations.users u
join dm_operations.dim_age_band a on a.age_band=u.age_band
left join dm_operations.dim_analysis_family f on f.analysis_family_key=u.analysis_family_key;

insert into dm_operations.daily_usage_segment
select :'batch_id'::uuid,d.date_key,u.current_plan_id,a.age_band_key,k.category_key,
  sum(c.data_usage_mb),count(distinct c.analysis_user_key),
  sum(c.data_usage_mb)/nullif(count(distinct c.analysis_user_key),0)
from dw_operations.content_usage c
join dw_operations.users u on u.analysis_user_key=c.analysis_user_key
join dm_operations.dim_age_band a on a.age_band=u.age_band
join dm_operations.dim_date d on d.calendar_date=c.usage_date
join dm_operations.dim_content_category k on k.content_category=c.content_category
group by d.date_key,u.current_plan_id,a.age_band_key,k.category_key;

insert into dm_operations.monthly_usage_segment
select :'batch_id'::uuid,to_char(d.calendar_month,'YYYYMMDD')::integer,
  u.current_plan_id,a.age_band_key,k.category_key,sum(c.data_usage_mb),
  count(distinct c.analysis_user_key),
  sum(c.data_usage_mb)/nullif(count(distinct c.analysis_user_key),0)
from dw_operations.content_usage c
join dw_operations.users u on u.analysis_user_key=c.analysis_user_key
join dm_operations.dim_age_band a on a.age_band=u.age_band
join dm_operations.dim_date d on d.calendar_date=c.usage_date
join dm_operations.dim_content_category k on k.content_category=c.content_category
group by d.calendar_month,u.current_plan_id,a.age_band_key,k.category_key;

insert into dm_operations.customer_daily_usage
select :'batch_id'::uuid,u.customer_key,d.date_key,sum(c.data_usage_mb)
from dw_operations.content_usage c
join dm_operations.dim_analysis_customer u on u.analysis_user_key=c.analysis_user_key
join dm_operations.dim_date d on d.calendar_date=c.usage_date
group by u.customer_key,d.date_key;

insert into dm_operations.customer_monthly_category_usage
select :'batch_id'::uuid,u.customer_key,to_char(d.calendar_month,'YYYYMMDD')::integer,
  k.category_key,sum(c.data_usage_mb)
from dw_operations.content_usage c
join dm_operations.dim_analysis_customer u on u.analysis_user_key=c.analysis_user_key
join dm_operations.dim_date d on d.calendar_date=c.usage_date
join dm_operations.dim_content_category k on k.content_category=c.content_category
group by u.customer_key,d.calendar_month,k.category_key;

insert into dm_operations.subscriber_current
select :'batch_id'::uuid,:'reference_date'::date,c.customer_key
from dm_operations.dim_analysis_customer c
where c.subscription_start_date<=:'reference_date'::date;

insert into dm_operations.family_current
select :'batch_id'::uuid,f.family_key,count(c.customer_key)::integer,
  f.has_bundle,f.has_kt_internet
from dm_operations.dim_analysis_family f
left join dm_operations.dim_analysis_customer c on c.family_key=f.family_key
group by f.family_key,f.has_bundle,f.has_kt_internet;

insert into dm_operations.customer_service_current
select :'batch_id'::uuid,c.customer_key,s.service_id,s.benefit_type,s.start_date
from dw_operations.user_services s
join dm_operations.dim_analysis_customer c on c.analysis_user_key=s.analysis_user_key
where s.start_date<=:'reference_date'::date;

insert into dm_operations.customer_discount_current
select distinct on(c.customer_key,d.discount_id)
  :'batch_id'::uuid,c.customer_key,d.discount_id,d.start_date
from dw_operations.user_discounts d
join dm_operations.dim_analysis_customer c on c.analysis_user_key=d.analysis_user_key
where d.status='ACTIVE' and d.start_date<=:'reference_date'::date
  and (d.end_date is null or d.end_date>=:'reference_date'::date)
order by c.customer_key,d.discount_id,d.start_date desc;
