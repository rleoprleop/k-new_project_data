-- 생성된 원본 CSV를 처리하는 로컬 PostgreSQL 15 이상용 기본 스키마.
-- 운영 DW와 개인화 DW는 generator/data/generated의 원본 CSV에서 생성한다.
create extension if not exists pgcrypto;

create schema if not exists audit;
create schema if not exists dw_common;
create schema if not exists landing;

create table if not exists audit.pipeline_run (
  batch_id uuid primary key default gen_random_uuid(),
  pipeline_name text not null default 'full_snapshot',
  run_type text not null default 'FULL_SNAPSHOT'
    check (run_type in ('FULL_SNAPSHOT','DATASET_INITIALIZATION','INCREMENTAL','CORRECTION')),
  source_set_checksum text not null,
  reference_date date not null,
  event_date_from date,
  event_date_to date,
  cutoff_date date,
  status text not null check (status in ('RUNNING','SUCCEEDED','FAILED')),
  started_at timestamptz not null default clock_timestamp(),
  ended_at timestamptz,
  error_message text,
  unique (pipeline_name, source_set_checksum),
  check (event_date_from is null or event_date_to is null or event_date_from<=event_date_to),
  check (event_date_to is null or cutoff_date is null or event_date_to<=cutoff_date)
);

create table if not exists audit.source_file (
  source_file_id bigint generated always as identity primary key,
  batch_id uuid not null references audit.pipeline_run(batch_id),
  source_name text not null,
  source_path text not null,
  event_date date,
  object_version text not null default '',
  sha256 text not null,
  row_count bigint,
  loaded_at timestamptz not null default clock_timestamp(),
  unique (batch_id, source_name, source_path, object_version)
);

create table if not exists audit.data_quality_result (
  batch_id uuid not null references audit.pipeline_run(batch_id),
  rule_name text not null,
  failed_row_count bigint not null check (failed_row_count >= 0),
  detail text,
  checked_at timestamptz not null default clock_timestamp(),
  primary key (batch_id, rule_name)
);
create table if not exists audit.ingestion_watermark (
  pipeline_name text primary key,
  last_successful_event_date date not null,
  last_successful_batch_id uuid not null references audit.pipeline_run(batch_id),
  updated_at timestamptz not null default clock_timestamp()
);

create or replace function audit.start_pipeline_run(
    p_checksum text,
    p_reference_date date,
    p_pipeline_name text default 'full_snapshot',
    p_run_type text default 'FULL_SNAPSHOT',
    p_event_date_from date default null,
    p_event_date_to date default null,
    p_cutoff_date date default null)
returns uuid language plpgsql as $$
declare v_batch_id uuid;
begin
  insert into audit.pipeline_run(
      pipeline_name,run_type,source_set_checksum,reference_date,event_date_from,event_date_to,
      cutoff_date,status)
  values (p_pipeline_name,p_run_type,p_checksum,p_reference_date,p_event_date_from,p_event_date_to,
      p_cutoff_date,'RUNNING')
  on conflict (pipeline_name,source_set_checksum) do update
    set status='RUNNING', started_at=clock_timestamp(), ended_at=null,
        error_message=null, reference_date=excluded.reference_date,run_type=excluded.run_type,
        event_date_from=excluded.event_date_from,event_date_to=excluded.event_date_to,
        cutoff_date=excluded.cutoff_date
  returning batch_id into v_batch_id;
  return v_batch_id;
end $$;
create or replace procedure audit.assert_zero(p_batch uuid, p_rule text, p_query text,
    p_detail text default null)
language plpgsql as $$
declare v_count bigint;
begin
  execute p_query into v_count;

  insert into audit.data_quality_result(batch_id,rule_name,failed_row_count,detail)
  values (p_batch,p_rule,coalesce(v_count,0),p_detail)
  on conflict(batch_id,rule_name)
      do update set failed_row_count=excluded.failed_row_count,
    detail=excluded.detail, checked_at=clock_timestamp();
  if coalesce(v_count,0) <> 0 then
    raise exception 'quality rule % failed with % row(s)', p_rule, v_count;
  end if;
end $$;

-- Raw 테이블은 원본의 자료형과 ID를 유지한다. COPY 적재 시 source_batch_id는
-- 트랜잭션 내부 설정값에서 가져오므로 클라이언트에서 행별로 처리할 필요가 없다.
create table if not exists landing.raw_users (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  user_id text not null, name text not null, age integer not null check(age between 8 and 120),
  gender text not null check(gender in ('F','M')), subscription_start_date date not null,
  current_plan_id text not null, family_id text, primary key(source_batch_id,user_id)
);

create table if not exists landing.raw_families (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  family_id text not null, has_bundle boolean not null, bundle_type text, has_kt_internet boolean not null,
  internet_product_group text, internet_contract_months integer, internet_status text,
  bundle_discount_method text, total_discount_allocation_method text, internet_benefit_discount_id text,
  primary key(source_batch_id,family_id)
);

create table if not exists landing.raw_bundle_discount_compositions (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  bundle_composition_id text not null, family_id text not null,
  component_type text not null check(component_type in ('INTERNET','MOBILE')), user_id text,
  component_role text not null, status text not null check(status in ('ACTIVE','ENDED')),
  start_date date not null, end_date date, primary key(source_batch_id,bundle_composition_id),
  check ((component_type='INTERNET' and user_id is null) or (component_type='MOBILE' and user_id is not null))
);

create table if not exists landing.raw_plans (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  plan_id text not null, plan_name text not null, plan_family text not null, plan_category text not null,
  monthly_fee numeric(12,2) not null check(monthly_fee>=0), data_limit_gb numeric(10,2),
  is_unlimited boolean not null, throttle_speed text, voice text, sms text,
  base_shared_data_gb numeric(10,2), is_rollover boolean not null, membership_tier text,
  choice_tier text, network_type text not null, device_discount_lines integer,
  data_sharing_discount_lines integer, family_bundle_eligible boolean not null,
  primary key(source_batch_id,plan_id),
  check ((is_unlimited and data_limit_gb is null) or (not is_unlimited and data_limit_gb>=0))
);

create table if not exists landing.raw_age_benefits (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  age_benefit_id text not null, benefit_name text not null, min_age numeric(5,1) not null,
  max_age numeric(5,1) not null, includes_safety_box boolean not null,
  primary key(source_batch_id,age_benefit_id), check(min_age<=max_age)
);

create table if not exists landing.raw_plan_age_benefits (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  plan_age_benefit_id text not null, plan_id text not null, age_benefit_id text not null,
  bonus_data_gb numeric(10,2), bonus_shared_data_gb numeric(10,2), bonus_voice_minutes numeric(10,1),
  bonus_sms_count numeric(10,1), bonus_video_minutes numeric(10,1),
  primary key(source_batch_id,plan_age_benefit_id), unique(source_batch_id,plan_id,age_benefit_id)
);

create table if not exists landing.raw_additional_services (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  service_id text not null, service_name text not null, service_category text not null,
  normal_monthly_price numeric(12,2), primary key(source_batch_id,service_id)
);

create table if not exists landing.raw_plan_benefits (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  plan_benefit_id text not null, plan_id text not null, service_id text not null,
  benefit_type text not null, benefit_value text, is_selectable boolean not null,
  option_group text, selection_count integer, primary key(source_batch_id,plan_benefit_id)
);

create table if not exists landing.raw_discounts (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  discount_id text not null, policy_domain text not null, benefit_code text not null,
  discount_name text not null, primary key(source_batch_id,discount_id)
);

create table if not exists landing.raw_internet_bundle_discount_rules (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  internet_bundle_rule_id text not null, discount_id text not null, bundle_discount_method text not null,
  rule_type text not null, internet_product_group text, contract_months integer,
  mobile_total_fee_min numeric(12,2), mobile_total_fee_max numeric(12,2),
  mobile_line_fee_min numeric(12,2), mobile_line_fee_max numeric(12,2), discount_target text not null,
  allocation_method text, discount_amount numeric(12,2), discount_rate numeric(8,5),
  effective_start_date date, effective_end_date date, primary key(source_batch_id,internet_bundle_rule_id)
);

create table if not exists landing.raw_premium_family_discount_rules (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  premium_family_rule_id text not null, discount_id text not null, benefit_type text not null,
  eligible_component_role text, requires_internet boolean not null, minimum_high_line_count integer,
  maximum_mobile_line_count integer, minimum_plan_fee numeric(12,2), required_network_type text,
  guardian_minimum_plan_fee numeric(12,2), guardian_required_network_type text,
  enrollment_min_age integer, enrollment_max_age integer, benefit_end_age integer,
  requires_legal_guardian boolean not null, discount_rate numeric(8,5), discount_amount numeric(12,2),
  effective_start_date date, effective_end_date date, primary key(source_batch_id,premium_family_rule_id)
);

create table if not exists landing.raw_user_discounts (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  user_discount_id text not null, user_id text not null, bundle_composition_id text not null,
  discount_id text not null, status text not null check(status in ('ACTIVE','ENDED')),
  start_date date not null, end_date date, primary key(source_batch_id,user_discount_id)
);

create table if not exists landing.raw_user_services (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  user_service_id text not null, user_id text not null, service_id text not null,
  benefit_type text not null check(benefit_type in ('CHOICE','PLUS','DOUBLE_CHOICE')),
  start_date date not null, primary key(source_batch_id,user_service_id)
);

create table if not exists landing.raw_content_usage (
  source_batch_id uuid not null default current_setting('pipeline.batch_id')::uuid,
  content_usage_id text not null, user_id text not null, usage_date date not null,
  content_category text not null check(content_category in ('video','short_form','music','ai','ebook',
      'web','sns','messaging','game','video_call','navigation','cloud','other')),
  content_detail text not null, data_usage_mb numeric(14,3) not null check(data_usage_mb>=0),
  primary key(source_batch_id,content_usage_id),
  unique(source_batch_id,user_id,usage_date,content_category,content_detail)
);

create index if not exists raw_content_usage_batch_date_idx on landing.raw_content_usage(source_batch_id,
    usage_date);

-- 개인정보가 없는 공통 마스터. 정책 데이터는 landing에서 자료형을 확인한 뒤
-- JSONB로 보관하여 두 DW에 정책 행을 중복 저장하지 않는다.
create table if not exists dw_common.plan (
  plan_id text primary key, plan_name text not null, plan_family text not null,
      plan_category text not null,
  monthly_fee numeric(12,2) not null, data_limit_gb numeric(10,2), is_unlimited boolean not null,
  throttle_speed text, voice text, sms text, base_shared_data_gb numeric(10,2),
      is_rollover boolean not null,
  membership_tier text, choice_tier text, network_type text not null, device_discount_lines integer,
  data_sharing_discount_lines integer, family_bundle_eligible boolean not null,
      source_batch_id uuid not null
);

create table if not exists dw_common.age_benefit (
    age_benefit_id text primary key,
    benefit_name text not null,
    min_age numeric(5,1) not null,
    max_age numeric(5,1) not null,
    includes_safety_box boolean not null,
    source_batch_id uuid not null
);

create table if not exists dw_common.additional_service (
    service_id text primary key,
    service_name text not null,
    service_category text not null,
    normal_monthly_price numeric(12,2),
    source_batch_id uuid not null
);

create table if not exists dw_common.discount (
    discount_id text primary key,
    policy_domain text not null,
    benefit_code text not null,
    discount_name text not null,
    source_batch_id uuid not null
);

create table if not exists dw_common.plan_age_benefit (
    plan_age_benefit_id text primary key,
    plan_id text not null references dw_common.plan(plan_id),
    age_benefit_id text not null references dw_common.age_benefit(age_benefit_id),
    policy jsonb not null,
    source_batch_id uuid not null
);

create table if not exists dw_common.plan_benefit (
    plan_benefit_id text primary key,
    plan_id text not null references dw_common.plan(plan_id),
    service_id text not null references dw_common.additional_service(service_id),
    policy jsonb not null,
    source_batch_id uuid not null
);

create table if not exists dw_common.internet_bundle_discount_rule (
    internet_bundle_rule_id text primary key,
    discount_id text not null references dw_common.discount(discount_id),
    policy jsonb not null,
    source_batch_id uuid not null
);

create table if not exists dw_common.premium_family_discount_rule (
    premium_family_rule_id text primary key,
    discount_id text not null references dw_common.discount(discount_id),
    policy jsonb not null,
    source_batch_id uuid not null
);
