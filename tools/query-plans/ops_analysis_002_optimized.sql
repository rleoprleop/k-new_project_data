-- Final OPS_ANALYSIS_002 query, matching the operational catalog.
-- Filter month_key and aggregate numeric customer/month keys before dimension joins.
-- Requires the permanent 130 view; statistics, zero fill and ordering match the baseline.
prepare kt_nd_ops_filtered_002 as
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
        total_usage_mb / 1024.0 as monthly_usage_gb
    from ai_operations.v_customer_monthly_usage_filtered_preagg
    where month_key >= (
        extract(year from $1::date)::integer * 10000
        + extract(month from $1::date)::integer * 100 + 1
    )
      and month_key < (
        extract(year from $2::date)::integer * 10000
        + extract(month from $2::date)::integer * 100 + 1
    )
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
