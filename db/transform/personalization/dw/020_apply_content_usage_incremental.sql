delete from dw_personalization.content_usage
where usage_date between current_setting('pipeline.event_date_from')::date
    and current_setting('pipeline.event_date_to')::date;

insert into dw_personalization.content_usage(
    source_batch_id,user_id,usage_date,content_category,content_detail,data_usage_mb)
select current_setting('pipeline.batch_id')::uuid,user_id,usage_date,content_category,
    content_detail,data_usage_mb
from landing.raw_content_usage
where source_batch_id=current_setting('pipeline.batch_id')::uuid;
