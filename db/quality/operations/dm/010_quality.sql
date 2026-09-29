call audit.assert_zero(:'batch_id'::uuid,'operations_dm_usage_total',$$
  select case when (select coalesce(sum(total_usage_mb),0) from dm_operations.daily_usage_segment)=
    (select coalesce(sum(data_usage_mb),0) from dw_operations.content_usage) then 0 else 1 end$$,
  'daily segment totals must reconcile to operations DW');
call audit.assert_zero(:'batch_id'::uuid,'operations_dm_monthly_total',$$
  select case when (select coalesce(sum(total_usage_mb),0) from dm_operations.monthly_usage_segment)=
    (select coalesce(sum(data_usage_mb),0) from dw_operations.content_usage) then 0 else 1 end$$,
  'monthly segment totals must reconcile to operations DW');
call audit.assert_zero(:'batch_id'::uuid,'operations_dm_active_subscriber',$$
  select case when (select count(*) from dm_operations.subscriber_current)=
    (select count(*) from dw_operations.users
      where subscription_start_date<=current_setting('pipeline.reference_date')::date)
    then 0 else 1 end$$,'active subscriber definition is subscription_start_date<=as_of_date');
call audit.assert_zero(:'batch_id'::uuid,'operations_dm_no_detail_dimension',$$
  select count(*) from information_schema.columns where table_schema='dm_operations'
    and column_name='content_detail'$$,'operations DM must not expose content_detail');
