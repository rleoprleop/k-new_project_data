call audit.assert_zero(:'batch_id'::uuid,'personalization_dm_incremental_daily_total',$$
  select case when (select coalesce(sum(f.total_usage_mb),0)
      from dm_personalization.customer_daily_usage f cross join incremental_context c
      where f.date_key between to_char(c.event_date_from,'YYYYMMDD')::integer
        and to_char(c.fact_rebuild_to,'YYYYMMDD')::integer)=
    (select coalesce(sum(u.data_usage_mb),0) from dw_personalization.content_usage u
      cross join incremental_context c where u.usage_date between c.event_date_from and c.fact_rebuild_to)
    then 0 else 1 end$$,'rebuilt customer daily totals must reconcile to DW');
call audit.assert_zero(:'batch_id'::uuid,'personalization_dm_incremental_monthly_total',$$
  select case when (select coalesce(sum(f.total_usage_mb),0)
      from dm_personalization.customer_monthly_usage f cross join incremental_context c
      where f.month_key between to_char(date_trunc('month',c.event_date_from),'YYYYMMDD')::integer
        and to_char(date_trunc('month',c.fact_rebuild_to),'YYYYMMDD')::integer)=
    (select coalesce(sum(u.data_usage_mb),0) from dw_personalization.content_usage u
      cross join incremental_context c
      where u.usage_date between date_trunc('month',c.event_date_from)::date and c.fact_rebuild_to)
    then 0 else 1 end$$,'rebuilt customer monthly totals must reconcile to DW');
