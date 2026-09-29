create schema if not exists dw_operations;

-- 운영 DW는 원본 14개 CSV의 논리 구조를 유지한다.
-- 사용자·가족·연결 행의 원본 ID와 이름은 저장하지 않고 HMAC 가명 키로 치환한다.
create table if not exists dw_operations.plans (
  source_batch_id uuid not null, plan_id text primary key, plan_name text not null,
  plan_family text not null, plan_category text not null, monthly_fee numeric(12,2) not null,
  data_limit_gb numeric(10,2), is_unlimited boolean not null, throttle_speed text,
  voice text, sms text, base_shared_data_gb numeric(10,2), is_rollover boolean not null,
  membership_tier text, choice_tier text, network_type text not null,
  device_discount_lines integer, data_sharing_discount_lines integer,
  family_bundle_eligible boolean not null
);

create table if not exists dw_operations.age_benefits (
  source_batch_id uuid not null, age_benefit_id text primary key, benefit_name text not null,
  min_age numeric(5,1) not null, max_age numeric(5,1) not null,
  includes_safety_box boolean not null
);

create table if not exists dw_operations.additional_services (
  source_batch_id uuid not null, service_id text primary key, service_name text not null,
  service_category text not null, normal_monthly_price numeric(12,2)
);

create table if not exists dw_operations.discounts (
  source_batch_id uuid not null, discount_id text primary key, policy_domain text not null,
  benefit_code text not null, discount_name text not null
);

create table if not exists dw_operations.plan_age_benefits (
  source_batch_id uuid not null, plan_age_benefit_id text primary key,
  plan_id text not null references dw_operations.plans(plan_id),
  age_benefit_id text not null references dw_operations.age_benefits(age_benefit_id),
  bonus_data_gb numeric(10,2), bonus_shared_data_gb numeric(10,2),
  bonus_voice_minutes numeric(10,1), bonus_sms_count numeric(10,1),
  bonus_video_minutes numeric(10,1), unique(plan_id,age_benefit_id)
);

create table if not exists dw_operations.plan_benefits (
  source_batch_id uuid not null, plan_benefit_id text primary key,
  plan_id text not null references dw_operations.plans(plan_id),
  service_id text not null references dw_operations.additional_services(service_id),
  benefit_type text not null, benefit_value text, is_selectable boolean not null,
  option_group text, selection_count integer
);

create table if not exists dw_operations.internet_bundle_discount_rules (
  source_batch_id uuid not null, internet_bundle_rule_id text primary key,
  discount_id text not null references dw_operations.discounts(discount_id),
  bundle_discount_method text not null, rule_type text not null, internet_product_group text,
  contract_months integer, mobile_total_fee_min numeric(12,2), mobile_total_fee_max numeric(12,2),
  mobile_line_fee_min numeric(12,2), mobile_line_fee_max numeric(12,2),
  discount_target text not null, allocation_method text, discount_amount numeric(12,2),
  discount_rate numeric(8,5), effective_start_date date, effective_end_date date
);

create table if not exists dw_operations.premium_family_discount_rules (
  source_batch_id uuid not null, premium_family_rule_id text primary key,
  discount_id text not null references dw_operations.discounts(discount_id),
  benefit_type text not null, eligible_component_role text, requires_internet boolean not null,
  minimum_high_line_count integer, maximum_mobile_line_count integer,
  minimum_plan_fee numeric(12,2), required_network_type text,
  guardian_minimum_plan_fee numeric(12,2), guardian_required_network_type text,
  enrollment_min_age integer, enrollment_max_age integer, benefit_end_age integer,
  requires_legal_guardian boolean not null, discount_rate numeric(8,5),
  discount_amount numeric(12,2), effective_start_date date, effective_end_date date
);

create table if not exists dw_operations.families (
  source_batch_id uuid not null, analysis_family_key text primary key,
  has_bundle boolean not null, bundle_type text, has_kt_internet boolean not null,
  internet_product_group text, internet_contract_months integer, internet_status text,
  bundle_discount_method text, total_discount_allocation_method text,
  internet_benefit_discount_id text
);

create table if not exists dw_operations.users (
  source_batch_id uuid not null, analysis_user_key text primary key,
  age_band text not null check(age_band in ('8-12','13-18','19-24','25-34','35-49','50-64','65+')),
  gender text not null check(gender in ('F','M')), subscription_start_date date not null,
  current_plan_id text not null references dw_operations.plans(plan_id),
  analysis_family_key text references dw_operations.families(analysis_family_key)
);

create table if not exists dw_operations.bundle_discount_compositions (
  source_batch_id uuid not null, analysis_bundle_composition_key text primary key,
  analysis_family_key text not null references dw_operations.families(analysis_family_key),
  component_type text not null, analysis_user_key text references dw_operations.users(analysis_user_key),
  component_role text not null, status text not null, start_date date not null, end_date date
);

create table if not exists dw_operations.user_discounts (
  source_batch_id uuid not null, analysis_user_discount_key text primary key,
  analysis_user_key text not null references dw_operations.users(analysis_user_key),
  analysis_bundle_composition_key text not null
    references dw_operations.bundle_discount_compositions(analysis_bundle_composition_key),
  discount_id text not null references dw_operations.discounts(discount_id),
  status text not null, start_date date not null, end_date date
);

create table if not exists dw_operations.user_services (
  source_batch_id uuid not null, analysis_user_service_key text primary key,
  analysis_user_key text not null references dw_operations.users(analysis_user_key),
  service_id text not null references dw_operations.additional_services(service_id),
  benefit_type text not null, start_date date not null
);

-- 운영 사용량의 grain: 가명 사용자 × 일자 × 카테고리. detail은 저장하지 않는다.
create table if not exists dw_operations.content_usage (
  source_batch_id uuid not null, analysis_user_key text not null
    references dw_operations.users(analysis_user_key), usage_date date not null,
  content_category text not null, data_usage_mb numeric(18,3) not null check(data_usage_mb>=0),
  primary key(analysis_user_key,usage_date,content_category)
);

create index if not exists operations_usage_date_idx
  on dw_operations.content_usage(usage_date);
create index if not exists operations_usage_user_date_idx
  on dw_operations.content_usage(analysis_user_key,usage_date);

revoke all on schema dw_operations from public;
