delete from dw_operations.content_usage
where usage_date between current_setting('pipeline.event_date_from')::date
  and current_setting('pipeline.event_date_to')::date;

insert into dw_operations.content_usage
select current_setting('pipeline.batch_id')::uuid,
  audit.analysis_key('user',user_id,'AUSR_'),usage_date,content_category,sum(data_usage_mb)
from stg_content_usage group by user_id,usage_date,content_category;
