-- Frozen preoptimization baseline for OPS_ANALYSIS_005.
-- Compare with ops_analysis_005_optimized.sql through the comparison/EXPLAIN entrypoints.
prepare kt_nd_ops_plan_005 as
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
ranked as (
    select
        calendar_month,
        analysis_user_key,
        monthly_usage_gb,
        row_number() over (
            partition by calendar_month
            order by monthly_usage_gb desc, analysis_user_key
        ) as usage_rank,
        count(*) over (
            partition by calendar_month
        ) as total_customer_count
    from customer_month
),
buckets(bucket_no, group_label, lower_gb, upper_gb) as (
    values
        (1, '0_to_1_gb', 0::numeric, 1::numeric),
        (2, '1_to_5_gb', 1::numeric, 5::numeric),
        (3, '5_to_10_gb', 5::numeric, 10::numeric),
        (4, '10_to_30_gb', 10::numeric, 30::numeric),
        (5, '30_to_100_gb', 30::numeric, 100::numeric),
        (6, '100_gb_or_more', 100::numeric, null::numeric)
),
distribution as (
    select
        m.calendar_month,
        'distribution'::text as result_type,
        b.group_label,
        b.bucket_no as sort_order,
        count(c.analysis_user_key)::bigint as customer_count,
        coalesce(sum(c.monthly_usage_gb), 0) as total_usage_gb
    from months m
    cross join buckets b
    left join customer_month c
        on c.calendar_month = m.calendar_month
       and c.monthly_usage_gb >= b.lower_gb
       and (b.upper_gb is null or c.monthly_usage_gb < b.upper_gb)
    group by m.calendar_month, b.group_label, b.bucket_no
),
concentration as (
    select
        m.calendar_month,
        'concentration'::text as result_type,
        format('top_%s_pct', (t.ratio * 100)::integer) as group_label,
        100 + (t.ratio * 100)::integer as sort_order,
        count(r.analysis_user_key)::bigint as customer_count,
        coalesce(sum(r.monthly_usage_gb), 0) as total_usage_gb
    from months m
    cross join unnest(array[0.01, 0.10]::numeric[]) as t(ratio)
    left join ranked r
        on r.calendar_month = m.calendar_month
       and r.usage_rank <= ceil(r.total_customer_count * t.ratio)
    group by m.calendar_month, t.ratio
),
grouped as (
    select * from distribution
    union all
    select * from concentration
),
totals as (
    select
        calendar_month,
        count(*)::bigint as customer_count,
        sum(monthly_usage_gb) as total_usage_gb
    from customer_month
    group by calendar_month
)
select
    g.calendar_month,
    g.result_type,
    g.group_label,
    g.customer_count,
    round(
        g.customer_count * 100.0 / nullif(t.customer_count, 0),
        2
    ) as customer_share_pct,
    round(g.total_usage_gb, 2) as total_usage_gb,
    round(
        g.total_usage_gb * 100.0 / nullif(t.total_usage_gb, 0),
        2
    ) as usage_share_pct
from grouped g
left join totals t using (calendar_month)
order by g.calendar_month, g.sort_order;
