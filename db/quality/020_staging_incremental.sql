call audit.assert_zero(:'batch_id'::uuid,'incremental_partition_date_match',$$
  select count(*) from incremental_content_usage where partition_event_date<>usage_date$$,
  'partition event date must equal usage_date');
call audit.assert_zero(:'batch_id'::uuid,'incremental_date_range',$$
  select count(*) from stg_content_usage
  where usage_date not between current_setting('pipeline.event_date_from')::date
    and current_setting('pipeline.event_date_to')::date$$,
  'all rows must be inside the requested range');
call audit.assert_zero(:'batch_id'::uuid,'incremental_user_fk',$$
  select count(*) from stg_content_usage s
  left join dw_personalization.users u on u.user_id=s.user_id where u.user_id is null$$,
  'content_usage.user_id must reference initialized users');
call audit.assert_zero(:'batch_id'::uuid,'incremental_manifest_rows',$$
  select case when (select count(*) from stg_content_usage)=
    (select coalesce(sum(row_count),0) from incremental_source_file) then 0 else 1 end$$,
  'manifest row counts must equal staged rows');
