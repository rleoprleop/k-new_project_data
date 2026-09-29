call audit.assert_zero(:'batch_id'::uuid,'personalization_dw_14_table_counts',$$
  select count(*) from (values
    ((select count(*) from dw_personalization.users),(select count(*) from stg_users)),
    ((select count(*) from dw_personalization.families),(select count(*) from stg_families)),
    ((select count(*) from dw_personalization.bundle_discount_compositions),(select count(*) from stg_bundle_discount_compositions)),
    ((select count(*) from dw_personalization.plans),(select count(*) from stg_plans)),
    ((select count(*) from dw_personalization.age_benefits),(select count(*) from stg_age_benefits)),
    ((select count(*) from dw_personalization.plan_age_benefits),(select count(*) from stg_plan_age_benefits)),
    ((select count(*) from dw_personalization.additional_services),(select count(*) from stg_additional_services)),
    ((select count(*) from dw_personalization.plan_benefits),(select count(*) from stg_plan_benefits)),
    ((select count(*) from dw_personalization.discounts),(select count(*) from stg_discounts)),
    ((select count(*) from dw_personalization.internet_bundle_discount_rules),(select count(*) from stg_internet_bundle_discount_rules)),
    ((select count(*) from dw_personalization.premium_family_discount_rules),(select count(*) from stg_premium_family_discount_rules)),
    ((select count(*) from dw_personalization.user_discounts),(select count(*) from stg_user_discounts)),
    ((select count(*) from dw_personalization.user_services),(select count(*) from stg_user_services)),
    ((select count(*) from dw_personalization.content_usage),(select count(*) from stg_content_usage
      where usage_date<=current_setting('pipeline.reference_date')::date-1))
  ) x(actual,expected) where actual<>expected$$,
  '13 master tables and cutoff-eligible content rows must match staging');
call audit.assert_zero(:'batch_id'::uuid,'personalization_dw_name_preserved',$$
  select count(*) from dw_personalization.users u join stg_users s using(user_id)
  where u.name<>s.name$$,'users.name must be retained in personalization DW');
call audit.assert_zero(:'batch_id'::uuid,'personalization_dw_detail_grain',$$
  select count(*) from (select user_id,usage_date,content_category,content_detail,count(*)
    from dw_personalization.content_usage group by 1,2,3,4 having count(*)>1) x$$,
  'personalization usage grain must be user/date/category/detail');
