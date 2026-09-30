-- 영구 저장 전에 세션 staging의 참조 무결성을 검증한다.
call audit.assert_zero(:'batch_id'::uuid,'staging_premium_family_age_integer',$$
  select count(*) from stg_premium_family_discount_rules r
  where exists (
    select 1 from (values
      (r.enrollment_min_age),(r.enrollment_max_age),(r.benefit_end_age)
    ) ages(age_value)
    where age_value is not null
      and (age_value not between -2147483648 and 2147483647
        or age_value<>trunc(age_value))
  )$$,'premium family ages must be null or exact values within the integer range');
call audit.assert_zero(:'batch_id'::uuid,'staging_age_benefit_range',$$
  select count(*) from stg_age_benefits
  where max_age is not null and max_age<min_age$$,
  'age benefit upper bound must be absent or at least the lower bound');
call audit.assert_zero(:'batch_id'::uuid,'staging_users_plan_fk',$$
  select count(*) from stg_users u left join stg_plans p on p.plan_id=u.current_plan_id
  where p.plan_id is null$$,'users.current_plan_id must reference plans');
call audit.assert_zero(:'batch_id'::uuid,'staging_users_family_fk',$$
  select count(*) from stg_users u left join stg_families f on f.family_id=u.family_id
  where u.family_id is not null and f.family_id is null$$,
  'non-null users.family_id must reference families');
call audit.assert_zero(:'batch_id'::uuid,'staging_usage_user_fk',$$
  select count(*) from stg_content_usage c left join stg_users u on u.user_id=c.user_id
  where u.user_id is null$$,'content_usage.user_id must reference users');
call audit.assert_zero(:'batch_id'::uuid,'staging_bundle_fk',$$
  select count(*) from stg_bundle_discount_compositions b
  left join stg_families f on f.family_id=b.family_id
  left join stg_users u on u.user_id=b.user_id
  where f.family_id is null or (b.user_id is not null and u.user_id is null)$$,
  'bundle family/user references must be valid');
call audit.assert_zero(:'batch_id'::uuid,'staging_plan_benefit_fk',$$
  select count(*) from stg_plan_benefits b
  left join stg_plans p on p.plan_id=b.plan_id
  left join stg_additional_services s on s.service_id=b.service_id
  where p.plan_id is null or s.service_id is null$$,'plan benefit references must be valid');
call audit.assert_zero(:'batch_id'::uuid,'staging_user_service_fk',$$
  select count(*) from stg_user_services x
  left join stg_users u on u.user_id=x.user_id
  left join stg_additional_services s on s.service_id=x.service_id
  where u.user_id is null or s.service_id is null$$,'user service references must be valid');
call audit.assert_zero(:'batch_id'::uuid,'staging_user_discount_fk',$$
  select count(*) from stg_user_discounts x
  left join stg_users u on u.user_id=x.user_id
  left join stg_bundle_discount_compositions b on b.bundle_composition_id=x.bundle_composition_id
  left join stg_discounts d on d.discount_id=x.discount_id
  where u.user_id is null or b.bundle_composition_id is null or d.discount_id is null$$,
  'user discount references must be valid');
call audit.assert_zero(:'batch_id'::uuid,'staging_usage_negative',$$
  select count(*) from stg_content_usage where data_usage_mb<0$$,
  'data_usage_mb must be non-negative');
