-- Case 3. Low data usage with a high-fee plan
-- Selection criteria and result interpretation: tools/README.md
-- Standalone SELECT returning at most 10 customers.
-- ASCII input; Unicode escapes preserve Korean result labels.
-- PostgreSQL standard_conforming_strings must be on (the default).
-- Actual database results have not been verified.

with latest as (
    select max(calendar_date) as end_date
    from ai_personalization.v_customer_month_daily_usage
),
usage_30d as (
    select
        u.user_id,
        sum(u.total_usage_mb) / 1024.0 as total_usage_gb
    from ai_personalization.v_customer_month_daily_usage u
    cross join latest l
    where u.calendar_date between l.end_date - 29 and l.end_date
    group by u.user_id
    having count(distinct u.calendar_date) = 30
)
select
    p.user_id,
    p.name,
    p.plan_name,
    p.monthly_fee,
    p.is_unlimited,
    round(u.total_usage_gb, 2) as usage_30d_gb,
    l.end_date as usage_end_date
from ai_personalization.v_customer_current_plan p
join usage_30d u on u.user_id = p.user_id
cross join latest l
where u.total_usage_gb < 15
  and p.monthly_fee >= 80000
order by p.monthly_fee desc, u.total_usage_gb, p.user_id
limit 10;
