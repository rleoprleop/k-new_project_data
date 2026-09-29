-- 개인화 DW와 원천 사용량의 합계를 검증한다.
-- 원본 가족 ID와 배치 ID 및 모든 가족 속성의 누락 여부를 대조한다.
call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'personalization_family_reconciliation', $$
  select count(*)
  from (select * from landing.raw_families
        where source_batch_id=current_setting('pipeline.batch_id')::uuid) r
  full join (select * from dw_personalization.family
             where source_batch_id=current_setting('pipeline.batch_id')::uuid) p
    on p.source_batch_id=r.source_batch_id and p.family_id=r.family_id
  where r.family_id is null or p.family_id is null
     or (r.has_bundle,r.bundle_type,r.has_kt_internet,r.internet_product_group,
         r.internet_contract_months,r.internet_status,r.bundle_discount_method,
         r.total_discount_allocation_method,r.internet_benefit_discount_id)
        is distinct from
        (p.has_bundle,p.bundle_type,p.has_kt_internet,p.internet_product_group,
         p.internet_contract_months,p.internet_status,p.bundle_discount_method,
         p.total_discount_allocation_method,p.internet_benefit_discount_id)$$,
  '개인화 가족 키·배치 ID·전체 속성이 Raw와 일치해야 한다');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'personalization_usage_reconciliation', $$
  select case when coalesce((select sum(data_usage_mb)
      from landing.raw_content_usage
      where source_batch_id=current_setting('pipeline.batch_id')::uuid),0)
                    = coalesce((select sum(data_usage_mb)
      from dw_personalization.content_usage
      where source_batch_id=current_setting('pipeline.batch_id')::uuid),0)
                    then 0 else 1 end$$,
  'raw and personalization usage sums must match');
