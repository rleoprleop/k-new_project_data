-- Supabase PostgreSQL initial load schema for generator/data/generated_analysis.
-- This is a landing zone: keep the CSV structure close to the source and do
-- not add foreign keys yet. DW/Mart constraints belong in later migrations.

create schema if not exists landing;

create table if not exists landing.users (
  analysis_user_key text primary key,
  age_band text not null,
  gender text not null,
  subscription_cohort text not null,
  tenure_months integer not null,
  current_plan_id text not null,
  analysis_family_key text
);

create table if not exists landing.families (
  analysis_family_key text primary key,
  has_bundle boolean not null,
  bundle_type text,
  has_kt_internet boolean not null,
  internet_product_group text,
  internet_contract_months integer,
  internet_status text,
  bundle_discount_method text,
  total_discount_allocation_method text,
  internet_benefit_discount_id text
);

create table if not exists landing.bundle_discount_compositions (
  analysis_bundle_composition_key text primary key,
  analysis_family_key text not null,
  component_type text not null,
  analysis_user_key text,
  component_role text not null,
  status text not null,
  start_month text not null,
  end_month text
);

create table if not exists landing.plans (
  plan_id text primary key,
  plan_name text not null,
  plan_family text not null,
  plan_category text not null,
  monthly_fee numeric(12, 2) not null,
  data_limit_gb numeric(10, 2),
  is_unlimited boolean not null,
  throttle_speed text,
  voice text,
  sms text,
  base_shared_data_gb numeric(10, 2),
  is_rollover boolean not null,
  membership_tier text,
  choice_tier text,
  network_type text not null,
  device_discount_lines integer,
  data_sharing_discount_lines integer,
  family_bundle_eligible boolean not null
);

create table if not exists landing.age_benefits (
  age_benefit_id text primary key,
  benefit_name text not null,
  min_age numeric(5, 1) not null,
  max_age numeric(5, 1) not null,
  includes_safety_box boolean not null
);

create table if not exists landing.plan_age_benefits (
  plan_age_benefit_id text primary key,
  plan_id text not null,
  age_benefit_id text not null,
  bonus_data_gb numeric(10, 2),
  bonus_shared_data_gb numeric(10, 2),
  bonus_voice_minutes numeric(10, 1),
  bonus_sms_count numeric(10, 1),
  bonus_video_minutes numeric(10, 1)
);

create table if not exists landing.additional_services (
  service_id text primary key,
  service_name text not null,
  service_category text not null,
  normal_monthly_price numeric(12, 2)
);

create table if not exists landing.plan_benefits (
  plan_benefit_id text primary key,
  plan_id text not null,
  service_id text not null,
  benefit_type text not null,
  benefit_value text,
  is_selectable boolean not null,
  option_group text,
  selection_count integer
);

create table if not exists landing.discounts (
  discount_id text primary key,
  policy_domain text not null,
  benefit_code text not null,
  discount_name text not null
);

create table if not exists landing.internet_bundle_discount_rules (
  internet_bundle_rule_id text primary key,
  discount_id text not null,
  bundle_discount_method text not null,
  rule_type text not null,
  internet_product_group text,
  contract_months integer,
  mobile_total_fee_min numeric(12, 2),
  mobile_total_fee_max numeric(12, 2),
  mobile_line_fee_min numeric(12, 2),
  mobile_line_fee_max numeric(12, 2),
  discount_target text not null,
  allocation_method text,
  discount_amount numeric(12, 2),
  discount_rate numeric(8, 5),
  effective_start_date date,
  effective_end_date date
);

create table if not exists landing.premium_family_discount_rules (
  premium_family_rule_id text primary key,
  discount_id text not null,
  benefit_type text not null,
  eligible_component_role text,
  requires_internet boolean not null,
  minimum_high_line_count integer,
  maximum_mobile_line_count integer,
  minimum_plan_fee numeric(12, 2),
  required_network_type text,
  guardian_minimum_plan_fee numeric(12, 2),
  guardian_required_network_type text,
  enrollment_min_age integer,
  enrollment_max_age integer,
  benefit_end_age integer,
  requires_legal_guardian boolean not null,
  discount_rate numeric(8, 5),
  discount_amount numeric(12, 2),
  effective_start_date date,
  effective_end_date date
);

create table if not exists landing.user_discounts (
  analysis_user_key text not null,
  analysis_bundle_composition_key text not null,
  discount_id text not null,
  status text not null,
  start_month text not null,
  end_month text,
  primary key (analysis_user_key, analysis_bundle_composition_key, discount_id, start_month)
);

create table if not exists landing.user_services (
  analysis_user_key text not null,
  service_id text not null,
  benefit_type text not null,
  start_month text not null,
  primary key (analysis_user_key, service_id, benefit_type, start_month)
);

create table if not exists landing.content_usage (
  analysis_user_key text not null,
  usage_date date not null,
  content_category text not null,
  content_detail text not null,
  data_usage_mb numeric(14, 3) not null,
  primary key (analysis_user_key, usage_date, content_category, content_detail)
);

-- Keep the landing zone inaccessible through browser-facing Supabase roles.
revoke all on schema landing from anon, authenticated;
revoke all on all tables in schema landing from anon, authenticated;

alter table landing.users enable row level security;
alter table landing.families enable row level security;
alter table landing.bundle_discount_compositions enable row level security;
alter table landing.plans enable row level security;
alter table landing.age_benefits enable row level security;
alter table landing.plan_age_benefits enable row level security;
alter table landing.additional_services enable row level security;
alter table landing.plan_benefits enable row level security;
alter table landing.discounts enable row level security;
alter table landing.internet_bundle_discount_rules enable row level security;
alter table landing.premium_family_discount_rules enable row level security;
alter table landing.user_discounts enable row level security;
alter table landing.user_services enable row level security;
alter table landing.content_usage enable row level security;
