-- Frozen preoptimization baseline for OPS_ANALYSIS_002.
-- Compare with ops_analysis_002_optimized.sql through the comparison/EXPLAIN entrypoints.
prepare kt_nd_ops_plan_002 as
with months as (
    select month_start::date as calendar_month
    from generate_series(
        $1::date::timestamp,
        ($2::date - interval '1 month')::timestamp,
        interval '1 month'
    ) as m(month_start)
),
customer_month as (
    select
        calendar_month,
        analysis_user_key,
        sum(total_usage_mb) / 1024.0 as monthly_usage_gb
    from ai_operations.v_customer_monthly_category_usage
    where calendar_month >= $1::date
      and calendar_month < $2::date
    group by calendar_month, analysis_user_key
),
monthly_stats as (
    select
        calendar_month,
        count(*) as recorded_customer_count,
        avg(monthly_usage_gb) as average_monthly_usage_gb,
        percentile_cont(0.5) within group (
            order by monthly_usage_gb
        ) as median_monthly_usage_gb
    from customer_month
    group by calendar_month
)
select
    m.calendar_month,
    coalesce(s.recorded_customer_count, 0)::bigint as recorded_customer_count,
    round(s.average_monthly_usage_gb, 2) as average_monthly_usage_gb,
    round(s.median_monthly_usage_gb::numeric, 2) as median_monthly_usage_gb
from months m
left join monthly_stats s using (calendar_month)
order by m.calendar_month;
