create schema if not exists dm_personalization;

create table if not exists dm_personalization.dim_date (
  date_key integer primary key, calendar_date date unique not null, calendar_month date not null,
  calendar_year integer not null, calendar_quarter integer not null,
  day_of_month integer not null, day_of_week integer not null, is_weekend boolean not null
);

create table if not exists dm_personalization.dim_plan (
  plan_id text primary key, plan_name text not null, plan_family text not null,
  plan_category text not null, monthly_fee numeric(12,2) not null,
  data_limit_gb numeric(10,2), is_unlimited boolean not null,
  choice_tier text, network_type text not null
);

create table if not exists dm_personalization.dim_content (
  content_key smallint generated always as identity primary key,
  content_category text not null, content_detail text not null,
  unique(content_category,content_detail)
);

create table if not exists dm_personalization.dim_family (
  family_key bigint generated always as identity primary key, family_id text unique not null,
  has_bundle boolean not null, bundle_type text, has_kt_internet boolean not null,
  internet_product_group text, internet_status text
);

-- 개인화 View와 고정 쿼리에서 user_id와 name을 함께 반환한다.
create table if not exists dm_personalization.dim_customer (
  customer_key bigint generated always as identity primary key, source_batch_id uuid not null,
  user_id text unique not null, name text not null,
  plan_id text not null references dm_personalization.dim_plan(plan_id),
  age integer not null, gender text not null, subscription_start_date date not null,
  family_key bigint references dm_personalization.dim_family(family_key)
);

create table if not exists dm_personalization.dim_service (
  service_id text primary key, service_name text not null, service_category text not null,
  normal_monthly_price numeric(12,2)
);

create table if not exists dm_personalization.dim_discount (
  discount_id text primary key, policy_domain text not null,
  benefit_code text not null, discount_name text not null
);

-- 선택 서비스와 생성기의 제한적 content_detail 매핑.
create table if not exists dm_personalization.bridge_service_content (
  service_id text not null references dm_personalization.dim_service(service_id),
  content_key smallint not null references dm_personalization.dim_content(content_key),
  primary key(service_id,content_key)
);

create table if not exists dm_personalization.customer_daily_usage (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_personalization.dim_customer(customer_key),
  date_key integer not null references dm_personalization.dim_date(date_key),
  total_usage_mb numeric(18,3) not null, month_to_date_usage_mb numeric(18,3) not null,
  primary key(customer_key,date_key)
);

create table if not exists dm_personalization.customer_monthly_usage (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_personalization.dim_customer(customer_key),
  month_key integer not null references dm_personalization.dim_date(date_key),
  total_usage_mb numeric(18,3) not null, average_daily_usage_mb numeric(18,3) not null,
  primary key(customer_key,month_key)
);

create table if not exists dm_personalization.customer_monthly_content_usage (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_personalization.dim_customer(customer_key),
  month_key integer not null references dm_personalization.dim_date(date_key),
  content_key smallint not null references dm_personalization.dim_content(content_key),
  total_usage_mb numeric(18,3) not null,
  primary key(customer_key,month_key,content_key)
);

create table if not exists dm_personalization.customer_service_current (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_personalization.dim_customer(customer_key),
  service_id text not null references dm_personalization.dim_service(service_id),
  benefit_type text not null, start_date date not null,
  primary key(customer_key,service_id,benefit_type)
);

create table if not exists dm_personalization.customer_discount_current (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_personalization.dim_customer(customer_key),
  discount_id text not null references dm_personalization.dim_discount(discount_id),
  start_date date not null, primary key(customer_key,discount_id)
);

create table if not exists dm_personalization.customer_family_current (
  source_batch_id uuid not null, customer_key bigint primary key
    references dm_personalization.dim_customer(customer_key),
  family_key bigint not null references dm_personalization.dim_family(family_key)
);

-- 5천만 건 이상 상세 사용량을 DM에 복제하지 않고 스타 형태의 상세 Fact View로 제공한다.
create or replace view dm_personalization.customer_content_daily_usage as
select u.source_batch_id,c.customer_key,d.date_key,k.content_key,u.data_usage_mb
from dw_personalization.content_usage u
join dm_personalization.dim_customer c on c.user_id=u.user_id
join dm_personalization.dim_date d on d.calendar_date=u.usage_date
join dm_personalization.dim_content k
  on (k.content_category,k.content_detail)=(u.content_category,u.content_detail);

create index if not exists personalization_customer_daily_date_idx
  on dm_personalization.customer_daily_usage(date_key);
create index if not exists personalization_monthly_usage_month_idx
  on dm_personalization.customer_monthly_usage(month_key);
create index if not exists personalization_monthly_content_month_idx
  on dm_personalization.customer_monthly_content_usage(month_key);

revoke all on schema dm_personalization from public;
