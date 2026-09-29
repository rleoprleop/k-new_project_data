-- 개인화 DW는 14개 CSV의 업무 키와 name/detail을 유지한다.
insert into dw_personalization.families select :'batch_id'::uuid,f.* from stg_families f;
insert into dw_personalization.users select :'batch_id'::uuid,u.* from stg_users u;
insert into dw_personalization.bundle_discount_compositions
  select :'batch_id'::uuid,b.* from stg_bundle_discount_compositions b;
insert into dw_personalization.user_discounts
  select :'batch_id'::uuid,d.* from stg_user_discounts d;
insert into dw_personalization.user_services
  select :'batch_id'::uuid,s.* from stg_user_services s;
insert into dw_personalization.content_usage
  select :'batch_id'::uuid,c.* from stg_content_usage c
  where c.usage_date<=:'reference_date'::date-1;
