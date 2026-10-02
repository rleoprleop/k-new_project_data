-- Case 1. YouTube usage and benefit mismatch
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
        sum(u.data_usage_mb) / 1024.0 as total_usage_gb,
        coalesce(
            sum(u.data_usage_mb) filter (
                where u.content_detail in (
                    'youtube_video',
                    'youtube_shorts',
                    'youtube_music'
                )
            ),
            0
        ) / 1024.0 as youtube_usage_gb
    from ai_personalization.v_customer_day_content_usage u
    cross join latest l
    where u.calendar_date between l.end_date - 29 and l.end_date
    group by u.user_id
    having count(distinct u.calendar_date) = 30
),
selected_services as (
    select
        user_id,
        string_agg(
            distinct service_name, ', ' order by service_name
        ) as current_services,
        bool_or(service_id = 'S002') as has_youtube_service
    from ai_personalization.v_customer_service_current
    group by user_id
),
youtube_benefit_plans as (
    select distinct plan_id
    from ai_personalization.v_plan_benefits
    where service_id = 'S002'
)
select
    p.user_id,
    p.name,
    p.plan_name,
    p.monthly_fee,
    p.is_unlimited,
    round(u.total_usage_gb, 2) as usage_30d_gb,
    round(u.youtube_usage_gb, 2) as youtube_30d_gb,
    round(
        u.youtube_usage_gb / nullif(u.total_usage_gb, 0) * 100,
        1
    ) as youtube_share_pct,
    coalesce(s.current_services, U&'\C120\D0DD \C11C\BE44\C2A4 \C5C6\C74C') as current_services,
    case
        when b.plan_id is not null
            then U&'\D604\C7AC \C694\AE08\C81C\C5D0\C11C YouTube \D61C\D0DD \C120\D0DD \AC00\B2A5\D558\C9C0\B9CC \BBF8\C120\D0DD'
        when p.is_unlimited
             and p.plan_family not in ('CHOICE', 'CHOICE_DOUBLE')
            then U&'\CD08\C774\C2A4 \C678 \BB34\C81C\D55C \C694\AE08\C81C\C774\BA70 YouTube \D61C\D0DD \C5C6\C74C'
        else U&'\D604\C7AC \C694\AE08\C81C\C5D0 YouTube \D61C\D0DD \C5C6\C74C'
    end as case_detail,
    l.end_date as usage_end_date
from ai_personalization.v_customer_current_plan p
join usage_30d u on u.user_id = p.user_id
left join selected_services s on s.user_id = p.user_id
left join youtube_benefit_plans b on b.plan_id = p.plan_id
cross join latest l
where u.youtube_usage_gb >= 20
  and u.youtube_usage_gb / nullif(u.total_usage_gb, 0) >= 0.30
  and not coalesce(s.has_youtube_service, false)
-- Optional: uncomment the next five predicates for non-Choice unlimited plans priced KRW 70,000-89,999.
--  and p.is_unlimited
--  and p.plan_family not in ('CHOICE', 'CHOICE_DOUBLE')
--  and p.monthly_fee >= 70000
--  and p.monthly_fee < 90000
--  and b.plan_id is null
order by u.youtube_usage_gb desc, p.user_id
limit 10;
