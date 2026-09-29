call audit.assert_zero(:'batch_id'::uuid,'personalization_dm_customer_name',$$
  select count(*) from dm_personalization.dim_customer c
  join dw_personalization.users u using(user_id) where c.name<>u.name$$,
  'dim_customer must retain name');
call audit.assert_zero(:'batch_id'::uuid,'personalization_dm_daily_total',$$
  select case when (select coalesce(sum(total_usage_mb),0) from dm_personalization.customer_daily_usage)=
    (select coalesce(sum(data_usage_mb),0) from dw_personalization.content_usage)
    then 0 else 1 end$$,'daily total must reconcile to DW');
call audit.assert_zero(:'batch_id'::uuid,'personalization_dm_monthly_total',$$
  select case when (select coalesce(sum(total_usage_mb),0) from dm_personalization.customer_monthly_usage)=
    (select coalesce(sum(data_usage_mb),0) from dw_personalization.content_usage)
    then 0 else 1 end$$,'monthly total must reconcile to DW');
call audit.assert_zero(:'batch_id'::uuid,'personalization_dm_detail_view_total',$$
  select case when (select coalesce(sum(data_usage_mb),0) from dm_personalization.customer_content_daily_usage)=
    (select coalesce(sum(data_usage_mb),0) from dw_personalization.content_usage)
    then 0 else 1 end$$,'detail star view must reconcile to DW');
call audit.assert_zero(:'batch_id'::uuid,'personalization_ai_name_present',$$
  select count(*) from information_schema.columns where table_schema='ai_personalization'
    and table_name in ('v_customer_month_daily_usage','v_customer_day_content_usage',
      'v_customer_monthly_usage','v_customer_monthly_category_usage',
      'v_customer_monthly_detail_usage','v_customer_current_plan')
    and column_name='name' having count(*)<>6$$,'personalization user views must include name');
