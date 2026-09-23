-- 운영 DW의 사용량 합계와 직접 식별 정보 부재를 검증한다.
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
