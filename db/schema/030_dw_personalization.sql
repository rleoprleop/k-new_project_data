create schema if not exists dw_personalization;

-- 개인화 데이터는 user_id를 유지하되 직접 식별 정보는 제한된 테이블에 한 번만 저장한다.
create table if not exists dw_personalization.customer_profile (
    source_batch_id uuid not null,
    user_id text not null,
    age integer not null,
    gender text not null,
    subscription_start_date date not null,
    current_plan_id text not null references dw_common.plan(plan_id),
    family_id text,
    primary key(source_batch_id,user_id)
);

create table if not exists dw_personalization.customer_identity_bridge (
    source_batch_id uuid not null,
    user_id text not null,
    name text not null,
    primary key(source_batch_id,user_id),
    foreign key(source_batch_id,user_id) references dw_personalization.customer_profile(source_batch_id,user_id)
);

create table if not exists dw_personalization.family (
    source_batch_id uuid not null,
    family_id text not null,
    attributes jsonb not null,
    primary key(source_batch_id,family_id)
);

create table if not exists dw_personalization.bundle_composition (
    source_batch_id uuid not null,
    bundle_composition_id text not null,
    family_id text not null,
    component_type text not null,
    user_id text,
    component_role text not null,
    status text not null,
    start_date date not null,
    end_date date,
    primary key(source_batch_id,bundle_composition_id)
);

create table if not exists dw_personalization.content_usage (
    source_batch_id uuid not null,
    user_id text not null,
    usage_date date not null,
    content_category text not null,
    content_detail text not null,
    data_usage_mb numeric(14,3) not null check(data_usage_mb>=0),
    primary key(source_batch_id,user_id,usage_date,content_category,content_detail)
);

create table if not exists dw_personalization.user_discount (
    source_batch_id uuid not null,
    user_id text not null,
    bundle_composition_id text not null,
    discount_id text not null,
    status text not null,
    start_date date not null,
    end_date date,
    primary key(source_batch_id,user_id,bundle_composition_id,discount_id,start_date)
);

create table if not exists dw_personalization.user_service (
    source_batch_id uuid not null,
    user_id text not null,
    service_id text not null,
    benefit_type text not null,
    start_date date not null,
    primary key(source_batch_id,user_id,service_id,benefit_type,start_date)
);

create index if not exists personalization_usage_batch_date_idx on dw_personalization.content_usage(source_batch_id,
    usage_date);

revoke all on schema dw_personalization from public;
revoke all on dw_personalization.customer_identity_bridge from public;
