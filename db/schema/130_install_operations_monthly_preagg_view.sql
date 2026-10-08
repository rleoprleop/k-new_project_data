-- Permanent migration of the measured customer/month numeric-preaggregation view.
-- Applied after 060/070/080 by full, initialize and incremental pipeline entrypoints.
-- Also supports direct installation with an object-owning DB account.
-- Idempotent; no source data, existing category view, index or role settings change.
-- Pipeline DDL commits before the data batch, like the existing schema migrations.
create or replace view ai_operations.v_customer_monthly_usage_filtered_preagg
with (security_invoker = false) as
with numeric_totals as (
    select f.month_key,
           f.customer_key,
           sum(f.total_usage_mb) as total_usage_mb
    from dm_operations.customer_monthly_category_usage f
    group by f.month_key, f.customer_key
)
select c.analysis_user_key,
       d.calendar_month,
       n.total_usage_mb,
       n.month_key
from numeric_totals n
join dm_operations.dim_analysis_customer c on c.customer_key = n.customer_key
join dm_operations.dim_date d on d.date_key = n.month_key;

revoke all on ai_operations.v_customer_monthly_usage_filtered_preagg from public;
grant select on ai_operations.v_customer_monthly_usage_filtered_preagg
    to role_operations_reader;

comment on view ai_operations.v_customer_monthly_usage_filtered_preagg is
    'Customer/month usage: aggregate numeric keys before dimension joins; filter exposed month_key before aggregation. Ordinary view, recomputed per query.';
