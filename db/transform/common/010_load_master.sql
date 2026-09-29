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
insert into dw_operations.premium_family_discount_rules
  select :'batch_id'::uuid,r.* from stg_premium_family_discount_rules r;
insert into dw_personalization.premium_family_discount_rules
  select :'batch_id'::uuid,r.* from stg_premium_family_discount_rules r;
