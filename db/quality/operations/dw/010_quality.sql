-- 운영 DW의 사용량 합계와 직접 식별 정보 부재를 검증한다.
-- 가족 키의 HMAC 가명화, 배치 ID, Raw의 모든 가족 속성을 함께 대조한다.
call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'operations_family_reconciliation', $$
  select count(*)
  from (select * from landing.raw_families
        where source_batch_id=current_setting('pipeline.batch_id')::uuid) r
  full join (select * from dw_operations.family
             where source_batch_id=current_setting('pipeline.batch_id')::uuid) o
    on o.source_batch_id=r.source_batch_id
   and o.analysis_family_key='AFAM_'||upper(substr(encode(hmac('family:'||r.family_id,
       current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24))
  where r.family_id is null or o.analysis_family_key is null
     or (r.has_bundle,r.bundle_type,r.has_kt_internet,r.internet_product_group,
         r.internet_contract_months,r.internet_status,r.bundle_discount_method,
         r.total_discount_allocation_method,r.internet_benefit_discount_id)
        is distinct from
        (o.has_bundle,o.bundle_type,o.has_kt_internet,o.internet_product_group,
         o.internet_contract_months,o.internet_status,o.bundle_discount_method,
         o.total_discount_allocation_method,o.internet_benefit_discount_id)$$,
  '운영 가족 키·배치 ID·전체 속성이 Raw와 일치해야 한다');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'operations_usage_reconciliation', $$
  select case when coalesce((select sum(data_usage_mb)
      from landing.raw_content_usage
      where source_batch_id=current_setting('pipeline.batch_id')::uuid),0)
                    = coalesce((select sum(data_usage_mb)
      from dw_operations.content_usage
      where source_batch_id=current_setting('pipeline.batch_id')::uuid),0)
                    then 0 else 1 end$$,
  'raw and operations usage sums must match');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'operations_no_direct_pii_column', $$
  select count(*) from information_schema.columns
  where table_schema in ('dw_operations','dm_operations') and column_name in ('user_id','name')$$,
  'operations schemas must not expose raw user_id or name');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid, 'operations_no_raw_user_id_value', $$
  select count(*) from dw_operations.customer o join landing.raw_users r
    on o.analysis_user_key=r.user_id and o.source_batch_id=r.source_batch_id
  where o.source_batch_id=current_setting('pipeline.batch_id')::uuid$$,
  'operations pseudonym key must never equal raw user_id');
