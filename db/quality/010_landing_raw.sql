-- DW 생성 전에 Raw 참조 관계와 사용량 제약을 검증한다.
call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'raw_users_plan_fk', $$
  select count(*) from landing.raw_users u left join landing.raw_plans p
    on p.source_batch_id=u.source_batch_id and p.plan_id=u.current_plan_id
  where u.source_batch_id=current_setting('pipeline.batch_id')::uuid and p.plan_id is null$$,
  'users.current_plan_id must reference plans');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'raw_users_family_fk', $$
  select count(*) from landing.raw_users u left join landing.raw_families f
    on f.source_batch_id=u.source_batch_id and f.family_id=u.family_id
 
      where u.source_batch_id=current_setting('pipeline.batch_id')::uuid
      and u.family_id is not null
      and f.family_id is null$$,
  'non-null users.family_id must reference families');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'raw_usage_user_fk', $$
  select count(*) from landing.raw_content_usage c left join landing.raw_users u
    on u.source_batch_id=c.source_batch_id and u.user_id=c.user_id
  where c.source_batch_id=current_setting('pipeline.batch_id')::uuid and u.user_id is null$$,
  'content_usage.user_id must reference users');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'raw_bundle_fk', $$
  select count(*) from landing.raw_bundle_discount_compositions b
  left join landing.raw_families f on (f.source_batch_id,f.family_id)=(b.source_batch_id,b.family_id)
  left join landing.raw_users u on (u.source_batch_id,u.user_id)=(b.source_batch_id,b.user_id)
  where b.source_batch_id=current_setting('pipeline.batch_id')::uuid
    and (f.family_id is null or (b.user_id is not null and u.user_id is null))$$,
  'bundle family/user references must be valid');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'raw_policy_fk', $$
  select count(*) from (
    select pab.plan_id
        from landing.raw_plan_age_benefits pab
        left join landing.raw_plans p on (p.source_batch_id,p.plan_id)=(pab.source_batch_id,pab.plan_id)
        where pab.source_batch_id=current_setting('pipeline.batch_id')::uuid and p.plan_id is null
    union all select pb.plan_id
        from landing.raw_plan_benefits pb
        left join landing.raw_plans p on (p.source_batch_id,p.plan_id)=(pb.source_batch_id,pb.plan_id)
        where pb.source_batch_id=current_setting('pipeline.batch_id')::uuid and p.plan_id is null
    union all select pb.service_id
        from landing.raw_plan_benefits pb
        left join landing.raw_additional_services s on (s.source_batch_id,
        s.service_id)=(pb.source_batch_id,pb.service_id)
        where pb.source_batch_id=current_setting('pipeline.batch_id')::uuid and s.service_id is null
  ) d$$,'plan policy references must be valid');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'raw_user_entitlement_fk', $$
  select count(*) from (
    select d.user_discount_id
        from landing.raw_user_discounts d
        left join landing.raw_users u on (u.source_batch_id,u.user_id)=(d.source_batch_id,d.user_id)
        where d.source_batch_id=current_setting('pipeline.batch_id')::uuid and u.user_id is null
    union all select d.user_discount_id
        from landing.raw_user_discounts d
        left join landing.raw_bundle_discount_compositions b on (b.source_batch_id,
        b.bundle_composition_id)=(d.source_batch_id,d.bundle_composition_id)
        where d.source_batch_id=current_setting('pipeline.batch_id')::uuid and b.bundle_composition_id is null
    union all select s.user_service_id
        from landing.raw_user_services s
        left join landing.raw_users u on (u.source_batch_id,u.user_id)=(s.source_batch_id,s.user_id)
        where s.source_batch_id=current_setting('pipeline.batch_id')::uuid and u.user_id is null
    union all select s.user_service_id
        from landing.raw_user_services s
        left join landing.raw_additional_services a on (a.source_batch_id,
        a.service_id)=(s.source_batch_id,s.service_id)
        where s.source_batch_id=current_setting('pipeline.batch_id')::uuid and a.service_id is null
  ) d$$,'discount and service references must be valid');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'raw_usage_duplicate_grain', $$
  select count(*) from (select 1 from landing.raw_content_usage
    where source_batch_id=current_setting('pipeline.batch_id')::uuid
    group by user_id,usage_date,content_category,content_detail
        having count(*)>1) d$$,
  'usage grain is user x date x category x detail');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'raw_usage_nonnegative', $$
  select count(*)
      from landing.raw_content_usage
      where source_batch_id=current_setting('pipeline.batch_id')::uuid and data_usage_mb<0$$,
  'data_usage_mb cannot be negative');
