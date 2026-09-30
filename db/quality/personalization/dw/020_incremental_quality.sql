call audit.assert_zero(:'batch_id'::uuid,'personalization_dw_incremental_rows',$$
  select case when (select count(*) from dw_personalization.content_usage
      where usage_date between current_setting('pipeline.event_date_from')::date
        and current_setting('pipeline.event_date_to')::date)=
    (select count(*) from stg_content_usage c
      join dw_personalization.users u using(user_id)
      where c.usage_date>=u.subscription_start_date) then 0 else 1 end$$,
  'personalization detail rows must match eligible staged rows');
call audit.assert_zero(:'batch_id'::uuid,'personalization_dw_incremental_total',$$
  select case when (select coalesce(sum(data_usage_mb),0) from dw_personalization.content_usage
      where usage_date between current_setting('pipeline.event_date_from')::date
        and current_setting('pipeline.event_date_to')::date)=
    (select coalesce(sum(c.data_usage_mb),0) from stg_content_usage c
      join dw_personalization.users u using(user_id)
      where c.usage_date>=u.subscription_start_date) then 0 else 1 end$$,
  'personalization incremental total must match eligible staging');
call audit.assert_zero(:'batch_id'::uuid,'personalization_dw_incremental_pre_subscription_usage',$$
  select count(*)
  from dw_personalization.content_usage c
  join dw_personalization.users u using(user_id)
  where c.usage_date between current_setting('pipeline.event_date_from')::date
      and current_setting('pipeline.event_date_to')::date
    and c.usage_date<u.subscription_start_date$$,
  'incremental personalization DW must exclude usage before subscription start');
