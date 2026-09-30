delete from dw_operations.content_usage
where usage_date between current_setting('pipeline.event_date_from')::date
  and current_setting('pipeline.event_date_to')::date;

insert into dw_operations.content_usage
select current_setting('pipeline.batch_id')::uuid,
  audit.analysis_key('user',c.user_id,'AUSR_'),c.usage_date,c.content_category,
  sum(c.data_usage_mb)
from stg_content_usage c
join dw_operations.users u
  on u.analysis_user_key=audit.analysis_key('user',c.user_id,'AUSR_')
where c.usage_date>=u.subscription_start_date
group by c.user_id,c.usage_date,c.content_category;
