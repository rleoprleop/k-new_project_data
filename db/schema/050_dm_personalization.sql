create schema if not exists dm_personalization;

create table if not exists dm_personalization.dim_date (
    date_key integer primary key,
    calendar_date date unique not null,
    calendar_month date not null,
    calendar_year integer not null,
    calendar_quarter integer not null,
    day_of_week integer not null,
    is_weekend boolean not null
);

create table if not exists dm_personalization.dim_plan (
    plan_id text primary key references dw_common.plan(plan_id),
    plan_name text not null,
    monthly_fee numeric(12,2) not null,
    data_limit_gb numeric(10,2),
    is_unlimited boolean not null
);

create table if not exists dm_personalization.dim_content (
    content_key smallint generated always as identity primary key,
    content_category text not null,
    content_detail text not null,
    unique(content_category,content_detail)
);

create table if not exists dm_personalization.dim_customer (
    customer_key bigint generated always as identity primary key,
    source_batch_id uuid not null,
    user_id text not null,
    current_plan_id text not null references dm_personalization.dim_plan(plan_id),
    age integer not null,
    gender text not null,
    subscription_start_date date not null,
    unique(user_id)
);

create table if not exists dm_personalization.fact_customer_daily_usage (
    source_batch_id uuid not null,
    customer_key bigint not null references dm_personalization.dim_customer(customer_key),
    usage_date date not null,
    plan_id text not null references dm_personalization.dim_plan(plan_id),
    content_key smallint not null references dm_personalization.dim_content(content_key),
    data_usage_mb numeric(18,3) not null,
    daily_total_usage_mb numeric(18,3) not null,
    month_to_date_usage_mb numeric(18,3) not null,
    quota_utilization numeric(18,8),
    primary key(customer_key,usage_date,content_key)
);

create table if not exists dm_personalization.customer_usage_feature_snapshot (
    source_batch_id uuid not null,
    user_id text not null,
    feature_reference_date date not null,
    trailing_7d_usage_mb numeric(18,3) not null,
    trailing_30d_usage_mb numeric(18,3) not null,
    content_category_usage_ratio jsonb not null,
    preferred_content_category text,
    month_to_date_usage_mb numeric(18,3) not null,
    plan_quota_utilization numeric(18,8),
    primary key(user_id,feature_reference_date)
);

create index if not exists personalization_daily_usage_date_idx
    on dm_personalization.fact_customer_daily_usage(usage_date);
create index if not exists personalization_daily_usage_batch_idx
    on dm_personalization.fact_customer_daily_usage(source_batch_id);
create index if not exists personalization_feature_date_idx
    on dm_personalization.customer_usage_feature_snapshot(feature_reference_date);
create index if not exists personalization_feature_batch_idx
    on dm_personalization.customer_usage_feature_snapshot(source_batch_id);

revoke all on schema dm_personalization from public;
