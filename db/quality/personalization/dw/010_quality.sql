-- 개인화 DW와 원천 사용량의 합계를 검증한다.
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
