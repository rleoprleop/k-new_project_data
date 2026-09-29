call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_personalization_dm_usage_reconciliation', $$
  select case when
    coalesce((select sum(data_usage_mb) from dw_personalization.content_usage
      where usage_date between current_setting('pipeline.event_date_from')::date
          and current_setting('pipeline.event_date_to')::date),0)
    =
    coalesce((select sum(data_usage_mb) from dm_personalization.fact_customer_daily_usage
      where usage_date between current_setting('pipeline.event_date_from')::date
          and current_setting('pipeline.event_date_to')::date),0)
  then 0 else 1 end$$,
  'incremental personalization DW and DM usage sums must match');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_feature_snapshot_completeness', $$
  select case when
    (select count(*) from dm_personalization.customer_usage_feature_snapshot f
      cross join incremental_context c
      where f.feature_reference_date between c.event_date_from and c.feature_rebuild_to)
    =
    (select count(*) from dm_personalization.dim_customer)
      * (select feature_rebuild_to-event_date_from+1 from incremental_context)
  then 0 else 1 end$$,
  'every customer must have one feature snapshot per rebuilt date');
