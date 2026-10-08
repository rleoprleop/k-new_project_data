-- Optional read-only checks for the manually installed 130 view migration.
-- Run separately as a DB owner/admin; no batch/audit writes and no pipeline wiring.
-- Full fact/view reconciliation is intentionally separate from performance timing.
with expected_columns(position, column_name, data_type) as (
    values (1, 'analysis_user_key', 'text'), (2, 'calendar_month', 'date'),
           (3, 'total_usage_mb', 'numeric'), (4, 'month_key', 'integer')
), actual_columns as (
    select ordinal_position as position, column_name, data_type
    from information_schema.columns
    where table_schema = 'ai_operations'
      and table_name = 'v_customer_monthly_usage_filtered_preagg'
), column_differences as (
    (select * from expected_columns except select * from actual_columns)
    union all
    (select * from actual_columns except select * from expected_columns)
), duplicate_grains as (
    select analysis_user_key, month_key
    from ai_operations.v_customer_monthly_usage_filtered_preagg
    group by analysis_user_key, month_key
    having count(*) <> 1
), fact_month_totals as (
    select d.calendar_month, sum(f.total_usage_mb) as total_usage_mb
    from dm_operations.customer_monthly_category_usage f
    join dm_operations.dim_date d on d.date_key = f.month_key
    group by d.calendar_month
), view_month_totals as (
    select calendar_month, sum(total_usage_mb) as total_usage_mb
    from ai_operations.v_customer_monthly_usage_filtered_preagg
    group by calendar_month
), total_differences as (
    select coalesce(f.calendar_month, v.calendar_month) as calendar_month
    from fact_month_totals f
    full join view_month_totals v using (calendar_month)
    where f.total_usage_mb is distinct from v.total_usage_mb
), permission_failures as (
    select r.role_name
    from (values ('role_operations_reader'), ('n8n_operations')) r(role_name)
    where not has_schema_privilege(r.role_name, 'ai_operations', 'USAGE')
       or not has_table_privilege(r.role_name,
           'ai_operations.v_customer_monthly_usage_filtered_preagg', 'SELECT')
       or has_table_privilege(r.role_name,
           'dm_operations.customer_monthly_category_usage', 'SELECT')
       or has_any_column_privilege(r.role_name,
           'dm_operations.customer_monthly_category_usage', 'SELECT')
), invalid_month_keys as (
    select month_key
    from dm_operations.customer_monthly_category_usage
    where month_key % 100 <> 1
), rules as (
    select 'view_column_contract' as rule_name, count(*) as failed_rows from column_differences
    union all
    select 'customer_month_grain', count(*) from duplicate_grains
    union all
    select 'monthly_usage_reconciliation', count(*) from total_differences
    union all
    select 'reader_view_only_access', count(*) from permission_failures
    union all
    select 'month_first_key', count(*) from invalid_month_keys
)
select rule_name, failed_rows,
       case when failed_rows = 0 then 'PASS' else 'FAIL' end as result
from rules order by rule_name;
