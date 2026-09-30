-- 개인정보가 없는 8개 마스터 CSV를 운영/개인화 DW에 각각 보관한다.
insert into dw_operations.plans select :'batch_id'::uuid,p.* from stg_plans p;
insert into dw_personalization.plans select :'batch_id'::uuid,p.* from stg_plans p;
insert into dw_operations.age_benefits select :'batch_id'::uuid,a.* from stg_age_benefits a;
insert into dw_personalization.age_benefits select :'batch_id'::uuid,a.* from stg_age_benefits a;
insert into dw_operations.additional_services
  select :'batch_id'::uuid,s.* from stg_additional_services s;
insert into dw_personalization.additional_services
  select :'batch_id'::uuid,s.* from stg_additional_services s;
insert into dw_operations.discounts select :'batch_id'::uuid,d.* from stg_discounts d;
insert into dw_personalization.discounts select :'batch_id'::uuid,d.* from stg_discounts d;
insert into dw_operations.plan_age_benefits
  select :'batch_id'::uuid,p.* from stg_plan_age_benefits p;
insert into dw_personalization.plan_age_benefits
  select :'batch_id'::uuid,p.* from stg_plan_age_benefits p;
insert into dw_operations.plan_benefits
  select :'batch_id'::uuid,p.* from stg_plan_benefits p;
insert into dw_personalization.plan_benefits
  select :'batch_id'::uuid,p.* from stg_plan_benefits p;
insert into dw_operations.internet_bundle_discount_rules
  select :'batch_id'::uuid,r.* from stg_internet_bundle_discount_rules r;
insert into dw_personalization.internet_bundle_discount_rules
  select :'batch_id'::uuid,r.* from stg_internet_bundle_discount_rules r;
-- staging 품질 검사로 소수 값·범위 초과를 거절한 뒤 정수 소수 표기만 변환한다. NULL은 유지한다.
insert into dw_operations.premium_family_discount_rules (
  source_batch_id,premium_family_rule_id,discount_id,benefit_type,eligible_component_role,
  requires_internet,minimum_high_line_count,maximum_mobile_line_count,minimum_plan_fee,
  required_network_type,guardian_minimum_plan_fee,guardian_required_network_type,
  enrollment_min_age,enrollment_max_age,benefit_end_age,requires_legal_guardian,
  discount_rate,discount_amount,effective_start_date,effective_end_date
)
  select :'batch_id'::uuid,r.premium_family_rule_id,r.discount_id,r.benefit_type,
    r.eligible_component_role,r.requires_internet,r.minimum_high_line_count,
    r.maximum_mobile_line_count,r.minimum_plan_fee,r.required_network_type,
    r.guardian_minimum_plan_fee,r.guardian_required_network_type,
    r.enrollment_min_age::integer,r.enrollment_max_age::integer,r.benefit_end_age::integer,
    r.requires_legal_guardian,r.discount_rate,r.discount_amount,
    r.effective_start_date,r.effective_end_date
  from stg_premium_family_discount_rules r;
insert into dw_personalization.premium_family_discount_rules (
  source_batch_id,premium_family_rule_id,discount_id,benefit_type,eligible_component_role,
  requires_internet,minimum_high_line_count,maximum_mobile_line_count,minimum_plan_fee,
  required_network_type,guardian_minimum_plan_fee,guardian_required_network_type,
  enrollment_min_age,enrollment_max_age,benefit_end_age,requires_legal_guardian,
  discount_rate,discount_amount,effective_start_date,effective_end_date
)
  select :'batch_id'::uuid,r.premium_family_rule_id,r.discount_id,r.benefit_type,
    r.eligible_component_role,r.requires_internet,r.minimum_high_line_count,
    r.maximum_mobile_line_count,r.minimum_plan_fee,r.required_network_type,
    r.guardian_minimum_plan_fee,r.guardian_required_network_type,
    r.enrollment_min_age::integer,r.enrollment_max_age::integer,r.benefit_end_age::integer,
    r.requires_legal_guardian,r.discount_rate,r.discount_amount,
    r.effective_start_date,r.effective_end_date
  from stg_premium_family_discount_rules r;
