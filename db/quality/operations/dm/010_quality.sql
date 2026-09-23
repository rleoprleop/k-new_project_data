-- 운영 DM과 운영 DW의 사용량 합계를 검증한다.
call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'operations_dm_usage_reconciliation', $$
  select case when coalesce((select sum(data_usage_mb)
      from dw_operations.content_usage
      where source_batch_id=current_setting('pipeline.batch_id')::uuid),0)
                    = coalesce((select sum(total_usage_mb)
      from dm_operations.fact_daily_usage_summary
      where source_batch_id=current_setting('pipeline.batch_id')::uuid),0)
                    then 0 else 1 end$$,
  'operations DW and DM usage sums must match');
