call audit.assert_zero(:'batch_id'::uuid,'operations_dw_incremental_total',$$
  select case when (select coalesce(sum(data_usage_mb),0) from dw_operations.content_usage
      where usage_date between current_setting('pipeline.event_date_from')::date
        and current_setting('pipeline.event_date_to')::date)=
    (select coalesce(sum(data_usage_mb),0) from stg_content_usage) then 0 else 1 end$$,
  'operations category aggregate must preserve incremental total');
call audit.assert_zero(:'batch_id'::uuid,'operations_dw_incremental_grain',$$
  select count(*) from (select analysis_user_key,usage_date,content_category,count(*)
    from dw_operations.content_usage
    where usage_date between current_setting('pipeline.event_date_from')::date
      and current_setting('pipeline.event_date_to')::date
    group by 1,2,3 having count(*)>1) x$$,'incremental operations grain must remain unique');
