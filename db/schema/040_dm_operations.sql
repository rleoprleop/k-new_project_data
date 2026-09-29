create schema if not exists dm_operations;

create table if not exists dm_operations.dim_date (
  date_key integer primary key, calendar_date date unique not null, calendar_month date not null,
  calendar_year integer not null, calendar_quarter integer not null,
  day_of_month integer not null, day_of_week integer not null, is_weekend boolean not null
);

create table if not exists dm_operations.dim_plan (
  plan_id text primary key, plan_name text not null, plan_family text not null,
  plan_category text not null, monthly_fee numeric(12,2) not null,
  data_limit_gb numeric(10,2), is_unlimited boolean not null
);

create table if not exists dm_operations.dim_age_band (
  age_band_key smallint primary key, age_band text unique not null,
  min_age integer not null, max_age integer
);

create table if not exists dm_operations.dim_content_category (
  category_key smallint generated always as identity primary key,
  content_category text unique not null
);

create table if not exists dm_operations.dim_analysis_family (
  family_key bigint generated always as identity primary key,
  analysis_family_key text unique not null, has_bundle boolean not null, bundle_type text,
  has_kt_internet boolean not null, internet_product_group text, internet_status text
);

create table if not exists dm_operations.dim_analysis_customer (
  customer_key bigint generated always as identity primary key,
  analysis_user_key text unique not null, plan_id text not null references dm_operations.dim_plan(plan_id),
  age_band_key smallint not null references dm_operations.dim_age_band(age_band_key),
  gender text not null, subscription_start_date date not null,
  family_key bigint references dm_operations.dim_analysis_family(family_key)
);

create table if not exists dm_operations.dim_service (
  service_id text primary key, service_name text not null, service_category text not null,
  normal_monthly_price numeric(12,2)
);

create table if not exists dm_operations.dim_discount (
  discount_id text primary key, policy_domain text not null,
  benefit_code text not null, discount_name text not null
);

-- 운영 집계 grain: 일자 × 현재 요금제 × 연령대 × 카테고리.
create table if not exists dm_operations.daily_usage_segment (
  source_batch_id uuid not null, date_key integer not null references dm_operations.dim_date(date_key),
  plan_id text not null references dm_operations.dim_plan(plan_id),
  age_band_key smallint not null references dm_operations.dim_age_band(age_band_key),
  category_key smallint not null references dm_operations.dim_content_category(category_key),
  total_usage_mb numeric(20,3) not null, usage_user_count integer not null,
  average_usage_mb numeric(20,3) not null,
  primary key(date_key,plan_id,age_band_key,category_key)
);

create table if not exists dm_operations.monthly_usage_segment (
  source_batch_id uuid not null, month_key integer not null references dm_operations.dim_date(date_key),
  plan_id text not null references dm_operations.dim_plan(plan_id),
  age_band_key smallint not null references dm_operations.dim_age_band(age_band_key),
  category_key smallint not null references dm_operations.dim_content_category(category_key),
  total_usage_mb numeric(20,3) not null, usage_user_count integer not null,
  average_usage_mb numeric(20,3) not null,
  primary key(month_key,plan_id,age_band_key,category_key)
);

create table if not exists dm_operations.customer_daily_usage (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_operations.dim_analysis_customer(customer_key),
  date_key integer not null references dm_operations.dim_date(date_key),
  total_usage_mb numeric(18,3) not null, primary key(customer_key,date_key)
);

create table if not exists dm_operations.customer_monthly_category_usage (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_operations.dim_analysis_customer(customer_key),
  month_key integer not null references dm_operations.dim_date(date_key),
  category_key smallint not null references dm_operations.dim_content_category(category_key),
  total_usage_mb numeric(18,3) not null,
  primary key(customer_key,month_key,category_key)
);

create table if not exists dm_operations.subscriber_current (
  source_batch_id uuid not null, as_of_date date not null,
  customer_key bigint primary key references dm_operations.dim_analysis_customer(customer_key)
);

create table if not exists dm_operations.family_current (
  source_batch_id uuid not null, family_key bigint primary key
    references dm_operations.dim_analysis_family(family_key), member_count integer not null,
  has_bundle boolean not null, has_kt_internet boolean not null
);

create table if not exists dm_operations.customer_service_current (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_operations.dim_analysis_customer(customer_key),
  service_id text not null references dm_operations.dim_service(service_id),
  benefit_type text not null, start_date date not null,
  primary key(customer_key,service_id,benefit_type)
);

create table if not exists dm_operations.customer_discount_current (
  source_batch_id uuid not null, customer_key bigint not null
    references dm_operations.dim_analysis_customer(customer_key),
  discount_id text not null references dm_operations.dim_discount(discount_id),
  start_date date not null, primary key(customer_key,discount_id)
);

create index if not exists operations_daily_segment_date_idx
  on dm_operations.daily_usage_segment(date_key);
create index if not exists operations_monthly_segment_month_idx
  on dm_operations.monthly_usage_segment(month_key);
create index if not exists operations_customer_daily_date_idx
  on dm_operations.customer_daily_usage(date_key);

revoke all on schema dm_operations from public;
