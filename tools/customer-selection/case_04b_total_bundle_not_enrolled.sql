-- 사례 4-B: 총액결합 미가입 고객
-- 선정 기준과 결과 해석: docs/customer-selection.md
-- 독립적으로 실행하는 조회 쿼리이며 최대 10명의 고객을 반환합니다.
-- 실제 DB 실행과 추출 건수는 아직 검증하지 않았습니다.

with members as (
    select
        u.user_id,
        u.name,
        u.family_id,
        p.plan_name,
        p.monthly_fee
    from dw_personalization.users u
    join dw_personalization.plans p
      on p.plan_id = u.current_plan_id
    where u.family_id is not null
      and p.family_bundle_eligible
),
family_stats as (
    select
        family_id,
        count(*) as member_count,
        sum(monthly_fee) as family_total_monthly_fee
    from members
    group by family_id
),
eligible_families as (
    select
        f.family_id,
        s.member_count,
        s.family_total_monthly_fee,
        f.internet_product_group,
        f.internet_contract_months,
        r.discount_amount as potential_family_mobile_discount
    from dw_personalization.families f
    join family_stats s on s.family_id = f.family_id
    join dw_personalization.internet_bundle_discount_rules r
      on r.discount_id = 'D001'
     and r.bundle_discount_method = 'TOTAL'
     and r.rule_type = 'MOBILE_TOTAL_POOL'
     and r.discount_target = 'MOBILE_POOL'
     and (
         r.internet_product_group = f.internet_product_group
         or r.internet_product_group = 'ANY'
     )
     and r.contract_months = f.internet_contract_months
     and (
         r.mobile_total_fee_min is null
         or s.family_total_monthly_fee >= r.mobile_total_fee_min
     )
     and (
         r.mobile_total_fee_max is null
         or s.family_total_monthly_fee <= r.mobile_total_fee_max
     )
    where not f.has_bundle
      and f.has_kt_internet
      and f.internet_status = 'ACTIVE'
      and s.member_count >= 2
      and r.discount_amount > 0
      and (
          r.effective_start_date is null
          or r.effective_start_date <= current_date
      )
      and (
          r.effective_end_date is null
          or r.effective_end_date >= current_date
      )
      and not exists (
          select 1
          from ai_personalization.v_customer_discount_current d
          join members fm on fm.user_id = d.user_id
          where fm.family_id = f.family_id
            and d.policy_domain in (
                'INTERNET_BUNDLE',
                'PREMIUM_FAMILY'
            )
      )
)
select
    m.user_id,
    m.name,
    m.plan_name,
    m.monthly_fee,
    e.family_id,
    e.member_count,
    e.family_total_monthly_fee,
    e.internet_product_group,
    e.internet_contract_months,
    e.potential_family_mobile_discount,
    '총액결합 미가입 고객' as case_detail
from members m
join eligible_families e on e.family_id = m.family_id
order by
    e.potential_family_mobile_discount desc,
    e.family_id,
    m.user_id
limit 10;
