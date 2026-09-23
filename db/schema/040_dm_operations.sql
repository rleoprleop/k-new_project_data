create schema if not exists dm_operations;

create table if not exists dm_operations.dim_date (
    date_key integer primary key,
    calendar_date date unique not null,
    calendar_month date not null,
    calendar_year integer not null,
    calendar_quarter integer not null,
    day_of_week integer not null,
    is_weekend boolean not null
);

create table if not exists dm_operations.dim_plan (
    plan_id text primary key references dw_common.plan(plan_id),
    plan_name text not null,
    plan_family text not null,
    plan_category text not null,
    monthly_fee numeric(12,2) not null,
    data_limit_gb numeric(10,2),
    is_unlimited boolean not null
);

create table if not exists dm_operations.dim_content (
    content_key smallint generated always as identity primary key,
    content_category text not null,
    content_detail text not null,
    unique(content_category,content_detail)
);

create table if not exists dm_operations.dim_age_band (
    age_band_key smallint primary key,
    age_band text unique not null,
    min_age integer not null,
    max_age integer
);

create table if not exists dm_operations.fact_daily_usage_summary (
    source_batch_id uuid not null,
    usage_date date not null,
    plan_id text not null references dm_operations.dim_plan(plan_id),
    age_band_key smallint not null references dm_operations.dim_age_band(age_band_key),
    content_key smallint not null references dm_operations.dim_content(content_key),
    total_usage_mb numeric(18,3) not null,
    active_user_count integer not null,
    average_usage_mb numeric(18,3) not null,
    usage_event_count bigint not null,
    primary key(source_batch_id,usage_date,plan_id,age_band_key,content_key)
);
