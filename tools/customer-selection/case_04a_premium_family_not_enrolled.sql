-- Case 4-A. Choice customers without premium family enrollment
-- Selection criteria and result interpretation: tools/README.md
-- Standalone SELECT returning at most 10 customers.
-- ASCII input; Unicode escapes preserve Korean result labels.
-- PostgreSQL standard_conforming_strings must be on (the default).
-- Actual database results have not been verified.

with premium_rule as (
    select
        minimum_plan_fee,
        minimum_high_line_count,
        maximum_mobile_line_count,
        discount_rate
    from dw_personalization.premium_family_discount_rules
    where discount_id = 'D003'
      and (
          effective_start_date is null
          or effective_start_date <= current_date
      )
      and (
          effective_end_date is null
          or effective_end_date >= current_date
      )
),
members as (
    select
        u.user_id,
        u.name,
        u.age,
        u.subscription_start_date,
        u.family_id,
        p.plan_name,
        p.plan_family,
        p.monthly_fee
    from dw_personalization.users u
    join dw_personalization.plans p
      on p.plan_id = u.current_plan_id
    where u.family_id is not null
      and p.family_bundle_eligible
),
family_stats as (
    select
        m.family_id,
        count(*) as member_count,
        count(*) filter (
            where m.monthly_fee >= r.minimum_plan_fee
        ) as high_fee_line_count
    from members m
    cross join premium_rule r
    group by m.family_id
),
ranked_high_members as (
    select
        m.*,
        row_number() over (
            partition by m.family_id
            order by
                m.monthly_fee,
                m.age desc,
                m.subscription_start_date,
                m.user_id
        ) as base_candidate_rank
    from members m
    cross join premium_rule r
    where m.monthly_fee >= r.minimum_plan_fee
)
select
    m.user_id,
    m.name,
    m.plan_name,
    m.monthly_fee,
    m.family_id,
    s.member_count,
    s.high_fee_line_count,
    round(m.monthly_fee * r.discount_rate, 0)
        as potential_premium_discount_per_month,
    U&'\D504\B9AC\BBF8\C5C4 \AC00\C871\ACB0\D569 \BBF8\AC00\C785 \CD08\C774\C2A4 \ACE0\AC1D' as case_detail
from ranked_high_members m
join family_stats s on s.family_id = m.family_id
join dw_personalization.families f on f.family_id = m.family_id
cross join premium_rule r
where not f.has_bundle
  and f.has_kt_internet
  and f.internet_status = 'ACTIVE'
  and f.internet_product_group = 'BASIC_ESSENCE_PREMIUM'
  and s.high_fee_line_count >= r.minimum_high_line_count
  and s.member_count <= r.maximum_mobile_line_count
  and m.plan_family in ('CHOICE', 'CHOICE_DOUBLE')
  and m.base_candidate_rank > 1
  and not exists (
      select 1
      from ai_personalization.v_customer_discount_current d
      where d.user_id = m.user_id
        and d.discount_id = 'D003'
  )
order by
    potential_premium_discount_per_month desc,
    m.family_id,
    m.user_id
limit 10;
