-- 공개 상품·할인 정책만 각 영역의 조회 역할에 직접 공개한다.
-- 고객·가족·사용량 테이블과 향후 추가되는 테이블에는 권한을 부여하지 않는다.
-- 060의 역할 생성 후 관리자/객체 소유자가 실행한다. 데이터 변경 없이 재실행 가능하다.
begin;

grant usage on schema dw_operations to role_operations_reader;
grant select on
    dw_operations.plans,
    dw_operations.age_benefits,
    dw_operations.plan_age_benefits,
    dw_operations.additional_services,
    dw_operations.plan_benefits,
    dw_operations.discounts,
    dw_operations.internet_bundle_discount_rules,
    dw_operations.premium_family_discount_rules
to role_operations_reader;

grant usage on schema dw_personalization to role_personalization_reader;
grant select on
    dw_personalization.plans,
    dw_personalization.age_benefits,
    dw_personalization.plan_age_benefits,
    dw_personalization.additional_services,
    dw_personalization.plan_benefits,
    dw_personalization.discounts,
    dw_personalization.internet_bundle_discount_rules,
    dw_personalization.premium_family_discount_rules
to role_personalization_reader;

commit;
