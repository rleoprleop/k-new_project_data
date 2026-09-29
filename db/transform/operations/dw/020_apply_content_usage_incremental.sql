delete from dw_operations.content_usage
where usage_date between current_setting('pipeline.event_date_from')::date
    and current_setting('pipeline.event_date_to')::date;

insert into dw_operations.content_usage(
    source_batch_id,analysis_user_key,usage_date,content_category,content_detail,data_usage_mb)
select current_setting('pipeline.batch_id')::uuid,
    'AUSR_'||upper(substr(encode(hmac('user:'||r.user_id,
        current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24)),
    r.usage_date,r.content_category,r.content_detail,r.data_usage_mb
from landing.raw_content_usage r
where r.source_batch_id=current_setting('pipeline.batch_id')::uuid;
