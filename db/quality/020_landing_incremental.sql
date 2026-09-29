call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_manifest_date_coverage', $$
  select count(*) from (
    select d::date event_date
    from generate_series(
        current_setting('pipeline.event_date_from')::date,
        current_setting('pipeline.event_date_to')::date,
        interval '1 day') d
    except
    select distinct event_date from incremental_source_file
  ) missing$$,
  'every requested date must have at least one source object');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_manifest_outside_range', $$
  select count(*) from incremental_source_file
  where event_date not between current_setting('pipeline.event_date_from')::date
      and current_setting('pipeline.event_date_to')::date$$,
  'manifest dates must stay inside the requested range');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_manifest_row_count', $$
  select case when
      (select coalesce(sum(row_count),0) from incremental_source_file)
      =
      (select count(*) from landing.raw_content_usage
       where source_batch_id=current_setting('pipeline.batch_id')::uuid)
    then 0 else 1 end$$,
  'manifest row counts must match copied rows');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_partition_date_match', $$
  select count(*) from incremental_content_usage
  where partition_event_date<>usage_date$$,
  'every row usage_date must match its source partition date');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_usage_date_range', $$
  select count(*) from landing.raw_content_usage
  where source_batch_id=current_setting('pipeline.batch_id')::uuid
    and usage_date not between current_setting('pipeline.event_date_from')::date
        and current_setting('pipeline.event_date_to')::date$$,
  'usage rows must stay inside the requested range');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_usage_future_date', $$
  select count(*) from landing.raw_content_usage
  where source_batch_id=current_setting('pipeline.batch_id')::uuid
    and usage_date>current_setting('pipeline.cutoff_date')::date$$,
  'future usage rows are forbidden');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_usage_user_fk', $$
  select count(*)
  from landing.raw_content_usage r
  left join dw_personalization.customer_profile p on p.user_id=r.user_id
  where r.source_batch_id=current_setting('pipeline.batch_id')::uuid
    and p.user_id is null$$,
  'incremental usage users must exist in the initialized customer snapshot');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_operations_user_key_fk', $$
  select count(*)
  from landing.raw_content_usage r
  left join dw_operations.customer c
    on c.analysis_user_key='AUSR_'||upper(substr(encode(hmac('user:'||r.user_id,
      current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24))
  where r.source_batch_id=current_setting('pipeline.batch_id')::uuid
    and c.analysis_user_key is null$$,
  'the pseudonymization key must match the initialized operations customer keys');

call audit.assert_zero(current_setting('pipeline.batch_id')::uuid,
    'incremental_usage_nonnegative', $$
  select count(*) from landing.raw_content_usage
  where source_batch_id=current_setting('pipeline.batch_id')::uuid and data_usage_mb<0$$,
  'data_usage_mb cannot be negative');
