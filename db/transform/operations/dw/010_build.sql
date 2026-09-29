-- 운영 DW의 가명 키 계산식은 생성기의 pseudonymize_key와 일치한다.
-- 접두사 + HMAC-SHA256(도메인 + ':' + 원본 ID)의 앞 24자리 16진수 대문자.
insert into dw_operations.family (
       source_batch_id,analysis_family_key,has_bundle,bundle_type,has_kt_internet,
       internet_product_group,internet_contract_months,internet_status,bundle_discount_method,
       total_discount_allocation_method,internet_benefit_discount_id)
select source_batch_id,
       'AFAM_'||upper(substr(encode(hmac('family:'||family_id,
           current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)),
       has_bundle,bundle_type,has_kt_internet,internet_product_group,internet_contract_months,
       internet_status,bundle_discount_method,total_discount_allocation_method,
       internet_benefit_discount_id
from landing.raw_families f where source_batch_id=:'batch_id'::uuid;

insert into dw_operations.customer
select source_batch_id,
       'AUSR_'||upper(substr(encode(hmac('user:'||user_id,current_setting('pipeline.pseudonymization_key'),
           'sha256'),'hex'),1,24)),
       case when age between 8 and 12 then '8-12' when age between 13 and 18 then '13-18'
            when age between 19 and 24 then '19-24' when age between 25 and 34 then '25-34'
            when age between 35 and 49 then '35-49' when age between 50 and 64 then '50-64' else '65+' end,
       gender,date_trunc('month',subscription_start_date)::date,
       ((extract(year from current_setting('pipeline.reference_date')::date)
         -extract(year from subscription_start_date))*12+
        (extract(month from current_setting('pipeline.reference_date')::date)
         -extract(month from subscription_start_date)))::integer,
       current_plan_id,
       case when family_id is null then null else 'AFAM_'||upper(substr(encode(hmac('family:'||family_id,
           current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)) end
from landing.raw_users where source_batch_id=:'batch_id'::uuid;

insert into dw_operations.bundle_composition
select source_batch_id,
       'ABND_'||upper(substr(encode(hmac('bundle_composition:'||bundle_composition_id,
           current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)),
       'AFAM_'||upper(substr(encode(hmac('family:'||family_id,
           current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)),
       component_type,
       case when user_id is null then null else 'AUSR_'||upper(substr(encode(hmac('user:'||user_id,
           current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)) end,
       component_role,status,date_trunc('month',start_date)::date,date_trunc('month',end_date)::date
from landing.raw_bundle_discount_compositions
    where source_batch_id=:'batch_id'::uuid;

insert into dw_operations.content_usage
select source_batch_id,'AUSR_'||upper(substr(encode(hmac('user:'||user_id,
    current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)),usage_date,
    content_category,content_detail,data_usage_mb
from landing.raw_content_usage where source_batch_id=:'batch_id'::uuid;

insert into dw_operations.user_discount
select source_batch_id,
       'AUSR_'||upper(substr(encode(hmac('user:'||user_id,current_setting('pipeline.pseudonymization_key'),
           'sha256'),'hex'),1,24)),
       'ABND_'||upper(substr(encode(hmac('bundle_composition:'||bundle_composition_id,
           current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)),
       discount_id,status,date_trunc('month',start_date)::date,date_trunc('month',end_date)::date
from landing.raw_user_discounts where source_batch_id=:'batch_id'::uuid;

insert into dw_operations.user_service
select source_batch_id,'AUSR_'||upper(substr(encode(hmac('user:'||user_id,
    current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)),service_id,
    benefit_type,date_trunc('month',start_date)::date
from landing.raw_user_services where source_batch_id=:'batch_id'::uuid;
