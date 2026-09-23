-- Add the approved privacy-limited content detail grain to existing landing DBs.
alter table landing.content_usage
  add column if not exists content_detail text;

-- Preserve any previously loaded category-only rows during the migration.
update landing.content_usage
set content_detail = content_category
where content_detail is null;

alter table landing.content_usage
  alter column content_detail set not null;

alter table landing.content_usage
  drop constraint if exists content_usage_pkey;

alter table landing.content_usage
  add primary key (analysis_user_key, usage_date, content_category, content_detail);
