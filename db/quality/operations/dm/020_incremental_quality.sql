call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_operations_dm_usage_reconciliation', $$
  select case when
    coalesce((select sum(data_usage_mb) from dw_operations.content_usage
      where usage_date between current_setting('pipeline.event_date_from')::date
          and current_setting('pipeline.event_date_to')::date),0)
    =
    coalesce((select sum(total_usage_mb) from dm_operations.fact_daily_usage_summary
      where usage_date between current_setting('pipeline.event_date_from')::date
          and current_setting('pipeline.event_date_to')::date),0)
  then 0 else 1 end$$,
  'incremental operations DW and DM usage sums must match');
