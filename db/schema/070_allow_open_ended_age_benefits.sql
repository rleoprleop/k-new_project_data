-- 020/030으로 생성한 기존 DW에도 적용한다. null max_age는 나이 상한 없음을 뜻한다.
-- 데이터·타입·하한은 변경하지 않는다. 이미 nullable이어도 재실행할 수 있다.
begin;
alter table dw_operations.age_benefits alter column max_age drop not null;
alter table dw_personalization.age_benefits alter column max_age drop not null;
commit;
