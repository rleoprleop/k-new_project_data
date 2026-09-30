-- 원본 CSV는 이 세션과 트랜잭션에서만 존재한다. 커밋/롤백 시 자동 삭제된다.
create temp table stg_users (
  user_id text primary key, name text not null, age integer not null,
  gender text not null, subscription_start_date date not null,
  current_plan_id text not null, family_id text
) on commit drop;
create temp table stg_families (
  family_id text primary key, has_bundle boolean not null, bundle_type text,
  has_kt_internet boolean not null, internet_product_group text,
  internet_contract_months integer, internet_status text, bundle_discount_method text,
  total_discount_allocation_method text, internet_benefit_discount_id text
) on commit drop;
create temp table stg_bundle_discount_compositions (
  bundle_composition_id text primary key, family_id text not null,
  component_type text not null, user_id text, component_role text not null,
  status text not null, start_date date not null, end_date date
) on commit drop;
create temp table stg_plans (
  plan_id text primary key, plan_name text not null, plan_family text not null,
  plan_category text not null, monthly_fee numeric(12,2) not null,
  data_limit_gb numeric(10,2), is_unlimited boolean not null, throttle_speed text,
  voice text, sms text, base_shared_data_gb numeric(10,2), is_rollover boolean not null,
  membership_tier text, choice_tier text, network_type text not null,
  device_discount_lines integer, data_sharing_discount_lines integer,
  family_bundle_eligible boolean not null
) on commit drop;
create temp table stg_age_benefits (
  age_benefit_id text primary key, benefit_name text not null,
  -- max_age가 null이면 나이 상한이 없는 혜택이다.
  min_age numeric(5,1) not null, max_age numeric(5,1),
  includes_safety_box boolean not null
) on commit drop;
create temp table stg_plan_age_benefits (
  plan_age_benefit_id text primary key, plan_id text not null, age_benefit_id text not null,
  bonus_data_gb numeric(10,2), bonus_shared_data_gb numeric(10,2),
  bonus_voice_minutes numeric(10,1), bonus_sms_count numeric(10,1),
  bonus_video_minutes numeric(10,1)
) on commit drop;
create temp table stg_additional_services (
  service_id text primary key, service_name text not null, service_category text not null,
  normal_monthly_price numeric(12,2)
) on commit drop;
create temp table stg_plan_benefits (
  plan_benefit_id text primary key, plan_id text not null, service_id text not null,
  benefit_type text not null, benefit_value text, is_selectable boolean not null,
  option_group text, selection_count integer
) on commit drop;
create temp table stg_discounts (
  discount_id text primary key, policy_domain text not null,
  benefit_code text not null, discount_name text not null
) on commit drop;
create temp table stg_internet_bundle_discount_rules (
  internet_bundle_rule_id text primary key, discount_id text not null,
  bundle_discount_method text not null, rule_type text not null, internet_product_group text,
  contract_months integer, mobile_total_fee_min numeric(12,2), mobile_total_fee_max numeric(12,2),
  mobile_line_fee_min numeric(12,2), mobile_line_fee_max numeric(12,2),
  discount_target text not null, allocation_method text, discount_amount numeric(12,2),
  discount_rate numeric(8,5), effective_start_date date, effective_end_date date
) on commit drop;
create temp table stg_premium_family_discount_rules (
  premium_family_rule_id text primary key, discount_id text not null, benefit_type text not null,
  eligible_component_role text, requires_internet boolean not null,
  minimum_high_line_count integer, maximum_mobile_line_count integer,
  minimum_plan_fee numeric(12,2), required_network_type text,
  guardian_minimum_plan_fee numeric(12,2), guardian_required_network_type text,
  enrollment_min_age integer, enrollment_max_age integer, benefit_end_age integer,
  requires_legal_guardian boolean not null, discount_rate numeric(8,5),
  discount_amount numeric(12,2), effective_start_date date, effective_end_date date
) on commit drop;
create temp table stg_user_discounts (
  user_discount_id text primary key, user_id text not null, bundle_composition_id text not null,
  discount_id text not null, status text not null, start_date date not null, end_date date
) on commit drop;
create temp table stg_user_services (
  user_service_id text primary key, user_id text not null, service_id text not null,
  benefit_type text not null, start_date date not null
) on commit drop;
create temp table stg_content_usage (
  content_usage_id text primary key, user_id text not null, usage_date date not null,
  content_category text not null, content_detail text not null,
  data_usage_mb numeric(14,3) not null check(data_usage_mb>=0),
  unique(user_id,usage_date,content_category,content_detail)
) on commit drop;
