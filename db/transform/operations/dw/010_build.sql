-- 운영 DW에는 HMAC 가명 키와 범주화된 속성만 저장한다.
insert into dw_operations.families
select :'batch_id'::uuid,audit.analysis_key('family',family_id,'AFAM_'),has_bundle,bundle_type,
  has_kt_internet,internet_product_group,internet_contract_months,internet_status,
  bundle_discount_method,total_discount_allocation_method,internet_benefit_discount_id
from stg_families;

insert into dw_operations.users
select :'batch_id'::uuid,audit.analysis_key('user',user_id,'AUSR_'),
  case when age between 8 and 12 then '8-12' when age between 13 and 18 then '13-18'
       when age between 19 and 24 then '19-24' when age between 25 and 34 then '25-34'
       when age between 35 and 49 then '35-49' when age between 50 and 64 then '50-64'
       else '65+' end,
  gender,subscription_start_date,current_plan_id,
  case when family_id is null then null
       else audit.analysis_key('family',family_id,'AFAM_') end
from stg_users;

insert into dw_operations.bundle_discount_compositions
select :'batch_id'::uuid,
  audit.analysis_key('bundle_composition',bundle_composition_id,'ABND_'),
  audit.analysis_key('family',family_id,'AFAM_'),component_type,
  case when user_id is null then null else audit.analysis_key('user',user_id,'AUSR_') end,
  component_role,status,start_date,end_date
from stg_bundle_discount_compositions;

insert into dw_operations.user_discounts
select :'batch_id'::uuid,audit.analysis_key('user_discount',user_discount_id,'AUDS_'),
  audit.analysis_key('user',user_id,'AUSR_'),
  audit.analysis_key('bundle_composition',bundle_composition_id,'ABND_'),
  discount_id,status,start_date,end_date
from stg_user_discounts;

insert into dw_operations.user_services
select :'batch_id'::uuid,audit.analysis_key('user_service',user_service_id,'AUSRVS_'),
  audit.analysis_key('user',user_id,'AUSR_'),service_id,benefit_type,start_date
from stg_user_services;

insert into dw_operations.content_usage
select :'batch_id'::uuid,audit.analysis_key('user',c.user_id,'AUSR_'),c.usage_date,
  c.content_category,sum(c.data_usage_mb)
from stg_content_usage c
join stg_users u on u.user_id=c.user_id
where c.usage_date between u.subscription_start_date and :'reference_date'::date-1
group by c.user_id,c.usage_date,c.content_category;
