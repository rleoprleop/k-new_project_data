-- 개인화 DM과 개인화 DW의 사용량 합계를 검증한다.
call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'personalization_dm_usage_reconciliation', $$
  select case when coalesce((select sum(data_usage_mb)
      from dw_personalization.content_usage
      where source_batch_id=current_setting('pipeline.batch_id')::uuid),0)
                    = coalesce((select sum(data_usage_mb)
      from dm_personalization.fact_customer_daily_usage
      where source_batch_id=current_setting('pipeline.batch_id')::uuid),0)
                    then 0 else 1 end$$,
  'personalization DW and DM usage sums must match');
