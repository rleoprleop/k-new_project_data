-- 공통 마스터를 충돌 시 갱신하는 방식으로 적재한다. -----------------------------
insert into dw_common.plan
select plan_id,plan_name,plan_family,plan_category,monthly_fee,data_limit_gb,is_unlimited,
       throttle_speed,voice,sms,base_shared_data_gb,is_rollover,membership_tier,choice_tier,
       network_type,device_discount_lines,data_sharing_discount_lines,family_bundle_eligible,source_batch_id
from landing.raw_plans where source_batch_id=:'batch_id'::uuid
on conflict(plan_id) do update set
 (plan_name,plan_family,plan_category,monthly_fee,data_limit_gb,is_unlimited,throttle_speed,voice,
     sms,base_shared_data_gb,is_rollover,membership_tier,choice_tier,network_type,
     device_discount_lines,data_sharing_discount_lines,family_bundle_eligible,source_batch_id)=
 (excluded.plan_name,excluded.plan_family,excluded.plan_category,excluded.monthly_fee,
     excluded.data_limit_gb,excluded.is_unlimited,excluded.throttle_speed,excluded.voice,
     excluded.sms,excluded.base_shared_data_gb,excluded.is_rollover,excluded.membership_tier,
     excluded.choice_tier,excluded.network_type,excluded.device_discount_lines,
     excluded.data_sharing_discount_lines,excluded.family_bundle_eligible,excluded.source_batch_id);

insert into dw_common.age_benefit
    select age_benefit_id,benefit_name,min_age,max_age,includes_safety_box,source_batch_id
    from landing.raw_age_benefits
    where source_batch_id=:'batch_id'::uuid
    on conflict(age_benefit_id)
    do update set (benefit_name,min_age,max_age,includes_safety_box,
    source_batch_id)=(excluded.benefit_name,excluded.min_age,excluded.max_age,
    excluded.includes_safety_box,excluded.source_batch_id);

insert into dw_common.additional_service
    select service_id,service_name,service_category,normal_monthly_price,source_batch_id
    from landing.raw_additional_services
    where source_batch_id=:'batch_id'::uuid
    on conflict(service_id)
    do update set (service_name,service_category,normal_monthly_price,
    source_batch_id)=(excluded.service_name,excluded.service_category,excluded.normal_monthly_price,
    excluded.source_batch_id);

insert into dw_common.discount
    select discount_id,policy_domain,benefit_code,discount_name,source_batch_id
    from landing.raw_discounts
    where source_batch_id=:'batch_id'::uuid
    on conflict(discount_id)
    do update set (policy_domain,benefit_code,discount_name,
    source_batch_id)=(excluded.policy_domain,excluded.benefit_code,excluded.discount_name,
    excluded.source_batch_id);

insert into dw_common.plan_age_benefit
    select plan_age_benefit_id,plan_id,age_benefit_id,
    to_jsonb(p)-'source_batch_id'-'plan_age_benefit_id'-'plan_id'-'age_benefit_id',source_batch_id
    from landing.raw_plan_age_benefits p
    where source_batch_id=:'batch_id'::uuid
    on conflict(plan_age_benefit_id)
    do update set (plan_id,age_benefit_id,policy,source_batch_id)=(excluded.plan_id,
    excluded.age_benefit_id,excluded.policy,excluded.source_batch_id);

insert into dw_common.plan_benefit
    select plan_benefit_id,plan_id,service_id,
    to_jsonb(p)-'source_batch_id'-'plan_benefit_id'-'plan_id'-'service_id',source_batch_id
    from landing.raw_plan_benefits p
    where source_batch_id=:'batch_id'::uuid
    on conflict(plan_benefit_id)
    do update set (plan_id,service_id,policy,source_batch_id)=(excluded.plan_id,excluded.service_id,
    excluded.policy,excluded.source_batch_id);

insert into dw_common.internet_bundle_discount_rule
    select internet_bundle_rule_id,discount_id,
    to_jsonb(r)-'source_batch_id'-'internet_bundle_rule_id'-'discount_id',source_batch_id
    from landing.raw_internet_bundle_discount_rules r
    where source_batch_id=:'batch_id'::uuid
    on conflict(internet_bundle_rule_id)
    do update set (discount_id,policy,source_batch_id)=(excluded.discount_id,excluded.policy,
    excluded.source_batch_id);

insert into dw_common.premium_family_discount_rule
    select premium_family_rule_id,discount_id,
    to_jsonb(r)-'source_batch_id'-'premium_family_rule_id'-'discount_id',source_batch_id
    from landing.raw_premium_family_discount_rules r
    where source_batch_id=:'batch_id'::uuid
    on conflict(premium_family_rule_id)
    do update set (discount_id,policy,source_batch_id)=(excluded.discount_id,excluded.policy,
    excluded.source_batch_id);
