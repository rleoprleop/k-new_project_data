delete from dw_personalization.content_usage
where usage_date between current_setting('pipeline.event_date_from')::date
  and current_setting('pipeline.event_date_to')::date;

insert into dw_personalization.content_usage
select current_setting('pipeline.batch_id')::uuid,c.* from stg_content_usage c;
