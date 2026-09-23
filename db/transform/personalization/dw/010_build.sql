-- 개인화 DW의 이름은 접근이 제한된 식별 연결 테이블에만 한 번 저장한다.
insert into dw_personalization.family
select source_batch_id,family_id,to_jsonb(f)-'source_batch_id'-'family_id'
    from landing.raw_families f
    where source_batch_id=:'batch_id'::uuid;

insert into dw_personalization.customer_profile
select source_batch_id,user_id,age,gender,subscription_start_date,current_plan_id,family_id
    from landing.raw_users
    where source_batch_id=:'batch_id'::uuid;

insert into dw_personalization.customer_identity_bridge
select source_batch_id,user_id,name
    from landing.raw_users
    where source_batch_id=:'batch_id'::uuid;

insert into dw_personalization.bundle_composition
select source_batch_id,bundle_composition_id,family_id,component_type,user_id,component_role,status,
    start_date,end_date
    from landing.raw_bundle_discount_compositions
    where source_batch_id=:'batch_id'::uuid;

insert into dw_personalization.content_usage
select source_batch_id,user_id,usage_date,content_category,content_detail,data_usage_mb
    from landing.raw_content_usage
    where source_batch_id=:'batch_id'::uuid;

insert into dw_personalization.user_discount
select source_batch_id,user_id,bundle_composition_id,discount_id,status,start_date,end_date
    from landing.raw_user_discounts
    where source_batch_id=:'batch_id'::uuid;

insert into dw_personalization.user_service
select source_batch_id,user_id,service_id,benefit_type,start_date
    from landing.raw_user_services
    where source_batch_id=:'batch_id'::uuid;
