-- S3/로컬 CSV 배치의 실행 이력만 영구 보관한다.
-- 원본 CSV는 각 배치 트랜잭션의 pg_temp staging에만 존재하며 Landing 스키마에는 저장하지 않는다.
create extension if not exists pgcrypto;

create schema if not exists audit;

create table if not exists audit.pipeline_run (
  batch_id uuid primary key default gen_random_uuid(),
  pipeline_name text not null default 'full_snapshot',
  run_type text not null default 'FULL_SNAPSHOT'
    check (run_type in ('FULL_SNAPSHOT','DATASET_INITIALIZATION','INCREMENTAL','CORRECTION')),
  source_set_checksum text not null,
  reference_date date not null,
  event_date_from date,
  event_date_to date,
  cutoff_date date,
  status text not null check (status in ('RUNNING','SUCCEEDED','FAILED')),
  started_at timestamptz not null default clock_timestamp(),
  ended_at timestamptz,
  error_message text,
  unique (pipeline_name,source_set_checksum),
  check (event_date_from is null or event_date_to is null or event_date_from<=event_date_to),
  check (event_date_to is null or cutoff_date is null or event_date_to<=cutoff_date)
);

create table if not exists audit.source_file (
  source_file_id bigint generated always as identity primary key,
  batch_id uuid not null references audit.pipeline_run(batch_id),
  source_name text not null,
  source_path text not null,
  event_date date,
  object_version text not null default '',
  sha256 text not null,
  row_count bigint,
  loaded_at timestamptz not null default clock_timestamp(),
  unique (batch_id,source_name,source_path,object_version)
);

create table if not exists audit.data_quality_result (
  batch_id uuid not null references audit.pipeline_run(batch_id),
  rule_name text not null,
  failed_row_count bigint not null check (failed_row_count>=0),
  detail text,
  checked_at timestamptz not null default clock_timestamp(),
  primary key (batch_id,rule_name)
);

create table if not exists audit.ingestion_watermark (
  pipeline_name text primary key,
  last_successful_event_date date not null,
  last_successful_batch_id uuid not null references audit.pipeline_run(batch_id),
  updated_at timestamptz not null default clock_timestamp()
);

create or replace function audit.start_pipeline_run(
    p_checksum text,
    p_reference_date date,
    p_pipeline_name text default 'full_snapshot',
    p_run_type text default 'FULL_SNAPSHOT',
    p_event_date_from date default null,
    p_event_date_to date default null,
    p_cutoff_date date default null)
returns uuid language plpgsql as $$
declare v_batch_id uuid;
begin
  insert into audit.pipeline_run(
      pipeline_name,run_type,source_set_checksum,reference_date,event_date_from,event_date_to,
      cutoff_date,status)
  values (p_pipeline_name,p_run_type,p_checksum,p_reference_date,p_event_date_from,p_event_date_to,
      p_cutoff_date,'RUNNING')
  on conflict (pipeline_name,source_set_checksum) do update
    set status='RUNNING',started_at=clock_timestamp(),ended_at=null,error_message=null,
        reference_date=excluded.reference_date,run_type=excluded.run_type,
        event_date_from=excluded.event_date_from,event_date_to=excluded.event_date_to,
        cutoff_date=excluded.cutoff_date
  returning batch_id into v_batch_id;
  return v_batch_id;
end $$;

create or replace procedure audit.assert_zero(
    p_batch uuid,p_rule text,p_query text,p_detail text default null)
language plpgsql as $$
declare v_count bigint;
begin
  execute p_query into v_count;
  insert into audit.data_quality_result(batch_id,rule_name,failed_row_count,detail)
  values (p_batch,p_rule,coalesce(v_count,0),p_detail)
  on conflict(batch_id,rule_name) do update
    set failed_row_count=excluded.failed_row_count,detail=excluded.detail,
        checked_at=clock_timestamp();
  if coalesce(v_count,0)<>0 then
    raise exception 'quality rule % failed with % row(s)',p_rule,v_count;
  end if;
end $$;

-- 운영 DW에 원본 ID를 남기지 않는 용도 분리 HMAC 키 함수.
create or replace function audit.analysis_key(p_domain text,p_raw_id text,p_prefix text)
returns text language sql stable strict as $$
  select p_prefix||upper(substr(encode(hmac(
      p_domain||':'||p_raw_id,current_setting('pipeline.pseudonymization_key'),'sha256'),'hex'),1,24))
$$;

revoke all on schema audit from public;
