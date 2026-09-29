create schema if not exists ai_operations;
create schema if not exists ai_personalization;

create or replace view ai_operations.v_subscriber_current as
select s.as_of_date,p.plan_id,p.plan_name,a.age_band,count(*)::integer subscriber_count
from dm_operations.subscriber_current s
join dm_operations.dim_analysis_customer c on c.customer_key=s.customer_key
join dm_operations.dim_plan p on p.plan_id=c.plan_id
join dm_operations.dim_age_band a on a.age_band_key=c.age_band_key
group by s.as_of_date,p.plan_id,p.plan_name,a.age_band;

create or replace view ai_operations.v_daily_usage_segment as
select d.calendar_date,p.plan_id,p.plan_name,a.age_band,k.content_category,
  f.total_usage_mb,f.usage_user_count,f.average_usage_mb
from dm_operations.daily_usage_segment f
join dm_operations.dim_date d on d.date_key=f.date_key
join dm_operations.dim_plan p on p.plan_id=f.plan_id
join dm_operations.dim_age_band a on a.age_band_key=f.age_band_key
join dm_operations.dim_content_category k on k.category_key=f.category_key;

create or replace view ai_operations.v_monthly_usage_segment as
select d.calendar_month,p.plan_id,p.plan_name,a.age_band,k.content_category,
  f.total_usage_mb,f.usage_user_count,f.average_usage_mb
from dm_operations.monthly_usage_segment f
join dm_operations.dim_date d on d.date_key=f.month_key
join dm_operations.dim_plan p on p.plan_id=f.plan_id
join dm_operations.dim_age_band a on a.age_band_key=f.age_band_key
join dm_operations.dim_content_category k on k.category_key=f.category_key;

create or replace view ai_operations.v_customer_daily_usage as
select c.analysis_user_key,d.calendar_date,f.total_usage_mb
from dm_operations.customer_daily_usage f
join dm_operations.dim_analysis_customer c on c.customer_key=f.customer_key
join dm_operations.dim_date d on d.date_key=f.date_key;

create or replace view ai_operations.v_customer_monthly_category_usage as
select c.analysis_user_key,d.calendar_month,k.content_category,f.total_usage_mb
from dm_operations.customer_monthly_category_usage f
join dm_operations.dim_analysis_customer c on c.customer_key=f.customer_key
join dm_operations.dim_date d on d.date_key=f.month_key
join dm_operations.dim_content_category k on k.category_key=f.category_key;

create or replace view ai_operations.v_family_current as
select f.analysis_family_key,x.member_count,x.has_bundle,x.has_kt_internet
from dm_operations.family_current x
join dm_operations.dim_analysis_family f on f.family_key=x.family_key;

create or replace view ai_operations.v_service_current as
select s.service_id,s.service_name,s.service_category,count(*)::integer customer_count
from dm_operations.customer_service_current x
join dm_operations.dim_service s on s.service_id=x.service_id
group by s.service_id,s.service_name,s.service_category;

create or replace view ai_operations.v_discount_current as
select d.discount_id,d.discount_name,d.policy_domain,count(*)::integer customer_count
from dm_operations.customer_discount_current x
join dm_operations.dim_discount d on d.discount_id=x.discount_id
group by d.discount_id,d.discount_name,d.policy_domain;

create or replace view ai_operations.v_plan_catalog as
select plan_id,plan_name,plan_family,plan_category,monthly_fee,data_limit_gb,is_unlimited
from dm_operations.dim_plan;

create or replace view ai_operations.v_plan_age_benefits as
select p.plan_id,p.plan_name,a.age_benefit_id,a.benefit_name,a.min_age,a.max_age,
  b.bonus_data_gb,b.bonus_shared_data_gb,b.bonus_voice_minutes,
  b.bonus_sms_count,b.bonus_video_minutes
from dw_operations.plan_age_benefits b
join dw_operations.plans p on p.plan_id=b.plan_id
join dw_operations.age_benefits a on a.age_benefit_id=b.age_benefit_id;

create or replace view ai_personalization.v_customer_month_daily_usage as
select c.user_id,c.name,d.calendar_month,d.calendar_date,f.total_usage_mb,
  f.month_to_date_usage_mb
from dm_personalization.customer_daily_usage f
join dm_personalization.dim_customer c on c.customer_key=f.customer_key
join dm_personalization.dim_date d on d.date_key=f.date_key;

create or replace view ai_personalization.v_customer_day_content_usage as
select c.user_id,c.name,d.calendar_date,k.content_category,k.content_detail,f.data_usage_mb
from dm_personalization.customer_content_daily_usage f
join dm_personalization.dim_customer c on c.customer_key=f.customer_key
join dm_personalization.dim_date d on d.date_key=f.date_key
join dm_personalization.dim_content k on k.content_key=f.content_key;

create or replace view ai_personalization.v_customer_monthly_usage as
select c.user_id,c.name,d.calendar_month,f.total_usage_mb,f.average_daily_usage_mb
from dm_personalization.customer_monthly_usage f
join dm_personalization.dim_customer c on c.customer_key=f.customer_key
join dm_personalization.dim_date d on d.date_key=f.month_key;

create or replace view ai_personalization.v_customer_monthly_category_usage as
select c.user_id,c.name,d.calendar_month,k.content_category,sum(f.total_usage_mb) total_usage_mb
from dm_personalization.customer_monthly_content_usage f
join dm_personalization.dim_customer c on c.customer_key=f.customer_key
join dm_personalization.dim_date d on d.date_key=f.month_key
join dm_personalization.dim_content k on k.content_key=f.content_key
group by c.user_id,c.name,d.calendar_month,k.content_category;

create or replace view ai_personalization.v_customer_monthly_detail_usage as
select c.user_id,c.name,d.calendar_month,k.content_category,k.content_detail,f.total_usage_mb
from dm_personalization.customer_monthly_content_usage f
join dm_personalization.dim_customer c on c.customer_key=f.customer_key
join dm_personalization.dim_date d on d.date_key=f.month_key
join dm_personalization.dim_content k on k.content_key=f.content_key;

create or replace view ai_personalization.v_customer_selected_service_usage as
select c.user_id,c.name,d.calendar_month,s.service_id,s.service_name,
  k.content_category,k.content_detail,f.total_usage_mb
from dm_personalization.customer_service_current cs
join dm_personalization.dim_customer c on c.customer_key=cs.customer_key
join dm_personalization.dim_service s on s.service_id=cs.service_id
join dm_personalization.bridge_service_content b on b.service_id=s.service_id
join dm_personalization.customer_monthly_content_usage f
  on f.customer_key=c.customer_key and f.content_key=b.content_key
join dm_personalization.dim_date d on d.date_key=f.month_key
join dm_personalization.dim_content k on k.content_key=f.content_key;

create or replace view ai_personalization.v_customer_current_plan as
select c.user_id,c.name,p.plan_id,p.plan_name,p.plan_family,p.plan_category,
  p.monthly_fee,p.data_limit_gb,p.is_unlimited,p.choice_tier,p.network_type
from dm_personalization.dim_customer c
join dm_personalization.dim_plan p on p.plan_id=c.plan_id;

create or replace view ai_personalization.v_customer_discount_current as
select c.user_id,c.name,d.discount_id,d.discount_name,d.policy_domain,x.start_date
from dm_personalization.customer_discount_current x
join dm_personalization.dim_customer c on c.customer_key=x.customer_key
join dm_personalization.dim_discount d on d.discount_id=x.discount_id;

create or replace view ai_personalization.v_customer_service_current as
select c.user_id,c.name,s.service_id,s.service_name,s.service_category,
  x.benefit_type,x.start_date
from dm_personalization.customer_service_current x
join dm_personalization.dim_customer c on c.customer_key=x.customer_key
join dm_personalization.dim_service s on s.service_id=x.service_id;

create or replace view ai_personalization.v_customer_family_current as
select c.user_id,c.name,f.family_id,f.has_bundle,f.bundle_type,
  f.has_kt_internet,f.internet_product_group,f.internet_status
from dm_personalization.customer_family_current x
join dm_personalization.dim_customer c on c.customer_key=x.customer_key
join dm_personalization.dim_family f on f.family_key=x.family_key;

create or replace view ai_personalization.v_plan_candidates as
select plan_id,plan_name,plan_family,plan_category,monthly_fee,data_limit_gb,
  is_unlimited,choice_tier,network_type from dm_personalization.dim_plan;

create or replace view ai_personalization.v_plan_benefits as
select p.plan_id,p.plan_name,b.benefit_type,b.benefit_value,b.is_selectable,
  b.option_group,b.selection_count,s.service_id,s.service_name,s.service_category
from dw_personalization.plan_benefits b
join dw_personalization.plans p on p.plan_id=b.plan_id
join dw_personalization.additional_services s on s.service_id=b.service_id;

-- 비밀번호는 저장소에 기록하지 않는다. 배포 시 비밀 관리 도구로 각 LOGIN에 설정한다.
do $$ begin
  if not exists(select 1 from pg_roles where rolname='role_operations_reader') then
    create role role_operations_reader nologin;
  end if;
  if not exists(select 1 from pg_roles where rolname='role_personalization_reader') then
    create role role_personalization_reader nologin;
  end if;
  if not exists(select 1 from pg_roles where rolname='n8n_operations') then
    create role n8n_operations login;
  end if;
  if not exists(select 1 from pg_roles where rolname='n8n_personalization') then
    create role n8n_personalization login;
  end if;
end $$;

grant role_operations_reader to n8n_operations;
grant role_personalization_reader to n8n_personalization;
alter role n8n_operations set default_transaction_read_only=on;
alter role n8n_operations set statement_timeout='30s';
alter role n8n_operations set idle_in_transaction_session_timeout='30s';
alter role n8n_personalization set default_transaction_read_only=on;
alter role n8n_personalization set statement_timeout='30s';
alter role n8n_personalization set idle_in_transaction_session_timeout='30s';
revoke all on schema dw_operations,dw_personalization,dm_operations,dm_personalization from public;
revoke all on schema ai_operations,ai_personalization from public;
grant usage on schema ai_operations to role_operations_reader;
grant select on all tables in schema ai_operations to role_operations_reader;
grant usage on schema ai_personalization to role_personalization_reader;
grant select on all tables in schema ai_personalization to role_personalization_reader;
alter default privileges in schema ai_operations
  grant select on tables to role_operations_reader;
alter default privileges in schema ai_personalization
  grant select on tables to role_personalization_reader;
