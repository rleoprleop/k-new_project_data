create schema if not exists dw_operations;

-- 운영 데이터에는 용도별 HMAC 가명 키만 저장하고 user_id/name 컬럼을 두지 않는다.
create table if not exists dw_operations.family (
    source_batch_id uuid not null,
    analysis_family_key text not null,
    has_bundle boolean not null,
    bundle_type text,
    has_kt_internet boolean not null,
    internet_product_group text,
    internet_contract_months integer,
    internet_status text,
    bundle_discount_method text,
    total_discount_allocation_method text,
    internet_benefit_discount_id text,
    primary key(source_batch_id,analysis_family_key)
);

create table if not exists dw_operations.customer (
    source_batch_id uuid not null,
    analysis_user_key text not null,
    age_band text not null check(age_band in ('8-12','13-18','19-24','25-34','35-49','50-64','65+')),
    gender text not null check(gender in ('F','M')),
    subscription_cohort date not null,
    tenure_months integer not null check(tenure_months>=0),
    current_plan_id text not null references dw_common.plan(plan_id),
    analysis_family_key text,
    primary key(source_batch_id,analysis_user_key),
    foreign key(source_batch_id,analysis_family_key)
        references dw_operations.family(source_batch_id,analysis_family_key)
        deferrable initially deferred
);

create table if not exists dw_operations.bundle_composition (
    source_batch_id uuid not null,
    analysis_bundle_composition_key text not null,
    analysis_family_key text not null,
    component_type text not null check(component_type in ('INTERNET','MOBILE')),
    analysis_user_key text,
    component_role text not null,
    status text not null check(status in ('ACTIVE','ENDED')),
    start_month date not null,
    end_month date,
    primary key(source_batch_id,analysis_bundle_composition_key),
    foreign key(source_batch_id,analysis_family_key)
        references dw_operations.family(source_batch_id,analysis_family_key),
    foreign key(source_batch_id,analysis_user_key) references dw_operations.customer(source_batch_id,analysis_user_key)
);

create table if not exists dw_operations.content_usage (
    source_batch_id uuid not null,
    analysis_user_key text not null,
    usage_date date not null,
    content_category text not null,
    content_detail text not null,
    data_usage_mb numeric(14,3) not null check(data_usage_mb>=0),
    primary key(source_batch_id,analysis_user_key,usage_date,content_category,content_detail),
    foreign key(source_batch_id,analysis_user_key) references dw_operations.customer(source_batch_id,analysis_user_key)
);

create table if not exists dw_operations.user_discount (
    source_batch_id uuid not null,
    analysis_user_key text not null,
    analysis_bundle_composition_key text not null,
    discount_id text not null references dw_common.discount(discount_id),
    status text not null,
    start_month date not null,
    end_month date,
    primary key(source_batch_id,analysis_user_key,analysis_bundle_composition_key,discount_id,start_month)
);

create table if not exists dw_operations.user_service (
    source_batch_id uuid not null,
    analysis_user_key text not null,
    service_id text not null references dw_common.additional_service(service_id),
    benefit_type text not null,
    start_month date not null,
    primary key(source_batch_id,analysis_user_key,service_id,benefit_type,start_month)
);

create index if not exists operations_usage_batch_date_idx on dw_operations.content_usage(source_batch_id,
    usage_date);
