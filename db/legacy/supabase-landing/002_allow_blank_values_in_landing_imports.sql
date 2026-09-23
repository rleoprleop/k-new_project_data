-- Supabase Dashboard CSV import sends blank cells as empty strings.
-- Keep nullable source values as text in the landing zone; DW transforms will
-- convert them with NULLIF(column, '')::numeric/date/integer later.

alter table landing.age_benefits
  alter column max_age drop not null,
  alter column max_age type text using max_age::text;

alter table landing.families
  alter column internet_contract_months type text using internet_contract_months::text;

alter table landing.plans
  alter column data_limit_gb type text using data_limit_gb::text;

alter table landing.internet_bundle_discount_rules
  alter column mobile_total_fee_min type text using mobile_total_fee_min::text,
  alter column mobile_total_fee_max type text using mobile_total_fee_max::text,
  alter column mobile_line_fee_min type text using mobile_line_fee_min::text,
  alter column mobile_line_fee_max type text using mobile_line_fee_max::text,
  alter column discount_rate type text using discount_rate::text,
  alter column effective_start_date type text using effective_start_date::text,
  alter column effective_end_date type text using effective_end_date::text;

alter table landing.premium_family_discount_rules
  alter column guardian_minimum_plan_fee type text using guardian_minimum_plan_fee::text,
  alter column enrollment_min_age type text using enrollment_min_age::text,
  alter column enrollment_max_age type text using enrollment_max_age::text,
  alter column benefit_end_age type text using benefit_end_age::text,
  alter column discount_rate type text using discount_rate::text,
  alter column discount_amount type text using discount_amount::text,
  alter column effective_start_date type text using effective_start_date::text,
  alter column effective_end_date type text using effective_end_date::text;
