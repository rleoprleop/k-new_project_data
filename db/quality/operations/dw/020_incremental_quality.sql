call audit.assert_zero(:'batch_id'::uuid,'operations_dw_incremental_total',$$
  select case when (select coalesce(sum(data_usage_mb),0) from dw_operations.content_usage
      where usage_date between current_setting('pipeline.event_date_from')::date
        and current_setting('pipeline.event_date_to')::date)=
    (select coalesce(sum(c.data_usage_mb),0)
      from stg_content_usage c
      join dw_operations.users u
        on u.analysis_user_key=audit.analysis_key('user',c.user_id,'AUSR_')
      where c.usage_date>=u.subscription_start_date) then 0 else 1 end$$,
  'operations category aggregate must preserve eligible incremental total');
call audit.assert_zero(:'batch_id'::uuid,'operations_dw_incremental_pre_subscription_usage',$$
  select count(*)
  from dw_operations.content_usage c
  join dw_operations.users u using(analysis_user_key)
  where c.usage_date between current_setting('pipeline.event_date_from')::date
      and current_setting('pipeline.event_date_to')::date
    and c.usage_date<u.subscription_start_date$$,
  'incremental operations DW must exclude usage before subscription start');
call audit.assert_zero(:'batch_id'::uuid,'operations_dw_incremental_grain',$$
  select count(*) from (select analysis_user_key,usage_date,content_category,count(*)
    from dw_operations.content_usage
    where usage_date between current_setting('pipeline.event_date_from')::date
      and current_setting('pipeline.event_date_to')::date
    group by 1,2,3 having count(*)>1) x$$,'incremental operations grain must remain unique');
