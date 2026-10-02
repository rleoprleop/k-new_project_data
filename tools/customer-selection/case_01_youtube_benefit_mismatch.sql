-- 사례 1: YouTube 사용과 선택 혜택 불일치
-- 선정 기준과 결과 해석: docs/customer-selection.md
-- 독립적으로 실행하는 조회 쿼리이며 최대 10명의 고객을 반환합니다.
-- 실제 DB 실행과 추출 건수는 아직 검증하지 않았습니다.

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
    coalesce(s.current_services, '선택 서비스 없음') as current_services,
    case
        when b.plan_id is not null
            then '현재 요금제에서 YouTube 혜택 선택 가능하지만 미선택'
        when p.is_unlimited
             and p.plan_family not in ('CHOICE', 'CHOICE_DOUBLE')
            then '초이스 외 무제한 요금제이며 YouTube 혜택 없음'
        else '현재 요금제에 YouTube 혜택 없음'
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
-- 초이스 미만의 7만~8만 원대 무제한 고객만 선정하려면 아래 다섯 조건의 주석을 해제합니다.
--  and p.is_unlimited
--  and p.plan_family not in ('CHOICE', 'CHOICE_DOUBLE')
--  and p.monthly_fee >= 70000
--  and p.monthly_fee < 90000
--  and b.plan_id is null
order by u.youtube_usage_gb desc, p.user_id
limit 10;
