call audit.assert_zero(:'batch_id'::uuid,'operations_dw_14_table_counts',$$
  select count(*) from (values
    ((select count(*) from dw_operations.users),(select count(*) from stg_users)),
    ((select count(*) from dw_operations.families),(select count(*) from stg_families)),
    ((select count(*) from dw_operations.bundle_discount_compositions),(select count(*) from stg_bundle_discount_compositions)),
    ((select count(*) from dw_operations.plans),(select count(*) from stg_plans)),
    ((select count(*) from dw_operations.age_benefits),(select count(*) from stg_age_benefits)),
    ((select count(*) from dw_operations.plan_age_benefits),(select count(*) from stg_plan_age_benefits)),
    ((select count(*) from dw_operations.additional_services),(select count(*) from stg_additional_services)),
    ((select count(*) from dw_operations.plan_benefits),(select count(*) from stg_plan_benefits)),
    ((select count(*) from dw_operations.discounts),(select count(*) from stg_discounts)),
    ((select count(*) from dw_operations.internet_bundle_discount_rules),(select count(*) from stg_internet_bundle_discount_rules)),
    ((select count(*) from dw_operations.premium_family_discount_rules),(select count(*) from stg_premium_family_discount_rules)),
    ((select count(*) from dw_operations.user_discounts),(select count(*) from stg_user_discounts)),
    ((select count(*) from dw_operations.user_services),(select count(*) from stg_user_services))
  ) x(actual,expected) where actual<>expected$$,'13 master/current-state tables must match staging');
call audit.assert_zero(:'batch_id'::uuid,'operations_dw_usage_total',$$
  select case when (select coalesce(sum(data_usage_mb),0) from dw_operations.content_usage)=
    (select coalesce(sum(data_usage_mb),0) from stg_content_usage
      where usage_date<=current_setting('pipeline.reference_date')::date-1) then 0 else 1 end$$,
  'category aggregation must preserve usage total');
call audit.assert_zero(:'batch_id'::uuid,'operations_dw_key_format',$$
  select count(*) from dw_operations.users where analysis_user_key !~ '^AUSR_[0-9A-F]{24}$'$$,
  'operations users must contain only HMAC analysis keys');
call audit.assert_zero(:'batch_id'::uuid,'operations_dw_category_grain',$$
  select count(*) from (select analysis_user_key,usage_date,content_category,count(*)
    from dw_operations.content_usage group by 1,2,3 having count(*)>1) x$$,
  'operations usage grain must be user/date/category');
