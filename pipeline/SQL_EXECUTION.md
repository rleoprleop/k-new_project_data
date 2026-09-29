# SQL 실행과 배치 운영

이 문서는 [`db/`](../db/README.md)의 SQL을 실행하는 파이프라인의 순서와 로컬 실행 방법을 설명합니다.

## 실행 순서

```text
원본 CSV checksum 계산
  → audit.pipeline_run 시작 / 동일 checksum의 batch ID 재사용
  → DDL 확인
  → Landing Raw 교체와 CSV \copy
  → Raw 품질 검사와 공통 마스터 갱신
  → 운영 DW·개인화 DW 생성
  → 운영 DM·개인화 DM 생성
  → 영역별 품질 검사
  → SUCCEEDED 기록과 커밋
```

| 단계 | 실행 파일 |
| --- | --- |
| 기반 DDL | [`db/schema/`](../db/schema/) |
| Landing 적재 | [`db/load/010_load_landing_raw.psql`](../db/load/010_load_landing_raw.psql) |
| 공통 마스터 | [`db/transform/common/010_load_master.sql`](../db/transform/common/010_load_master.sql) |
| 운영·개인화 DW/DM 변환 | [`db/transform/`](../db/transform/) |
| 품질 검사 | [`db/quality/`](../db/quality/) |

## 로컬 실행

PostgreSQL 15 이상, `psql`, `pgcrypto` 생성 권한과 DDL/DML 권한이 필요합니다. 저장소 루트에서 실행합니다.

```powershell
$env:KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY = "secret-managed-outside-repository"
.\pipeline\scripts\run_pipeline.ps1 `
  -ConnectionString "postgresql://postgres:postgres@localhost:5432/kt_nd"
```

체크인되지 않은 합성 데이터의 기본 HMAC 키를 사용하는 로컬 테스트에서는 다음 명령을 사용합니다.

```powershell
.\pipeline\scripts\run_pipeline.ps1 `
  -ConnectionString "postgresql://postgres:postgres@localhost:5432/kt_nd" `
  -AllowSyntheticDefaultKey
```

`-RawDirectory`와 `-ReferenceDate`로 입력 파일 위치와 기준일을 변경할 수 있습니다. 실제 비밀은 명령행 인자로 전달하지 말고, 배포 환경의 비밀 관리 도구로 전달해야 합니다.

## 일일 증분 실행

먼저 `content_usage`를 제외한 13개 스냅샷 파일로 고객·가족·상품 상태를 초기화합니다.

```powershell
.\pipeline\scripts\initialize_incremental_pipeline.ps1 `
  -ConnectionString "postgresql://postgres:postgres@localhost:5432/kt_nd" `
  -RawDirectory ".\generator\data\generated" `
  -ReferenceDate "2026-09-29" `
  -AllowSyntheticDefaultKey
```

그 다음 생성기의 S3형 날짜 파티션에서 성공 워터마크 다음 날부터
`ProcessingDate - 1`까지 처리합니다. 한 실행에서 기본 7일씩 커밋합니다.

```powershell
.\pipeline\scripts\run_incremental_pipeline.ps1 `
  -ConnectionString "postgresql://postgres:postgres@localhost:5432/kt_nd" `
  -ContentRoot ".\generator\data\generated\raw\content_usage" `
  -ProcessingDate "2026-09-30" `
  -AllowSyntheticDefaultKey
```

`ProcessingDate=2026-09-30`이면 `2026-09-29`까지만 적재합니다. 파일 선택뿐 아니라
SQL 품질 검사에서도 미래 `usage_date`를 거부합니다. 날짜 중간에 파티션이 없으면
후속 날짜를 처리하지 않고 실패합니다.

과거 날짜 정정 파일은 기존 파일을 덮어쓰지 않고 다음처럼 버전 디렉터리에 둡니다.

```text
raw/content_usage/event_date=2026-09-20/run_id=fix-001/part-000.csv
```

```powershell
.\pipeline\scripts\run_incremental_pipeline.ps1 `
  -ConnectionString "postgresql://postgres:postgres@localhost:5432/kt_nd" `
  -ContentRoot ".\generator\data\generated\raw\content_usage" `
  -ProcessingDate "2026-09-30" `
  -CorrectionDate "2026-09-20" `
  -CorrectionVersion "fix-001" `
  -AllowSyntheticDefaultKey
```

정정 파일은 해당 날짜 전체를 담은 대체 파티션입니다. 워터마크는 이동하지 않으며,
정정일부터 월말까지의 월 누적 Fact와 최대 30일 영향 범위의 추천 Feature를 다시 만듭니다.

## 감사 조회

```sql
select batch_id, pipeline_name, run_type, source_set_checksum, reference_date,
       event_date_from, event_date_to, cutoff_date, status, started_at, ended_at, error_message
from audit.pipeline_run
order by started_at desc;

select source_name, sha256, row_count, loaded_at
from audit.source_file
where batch_id = '<batch-id>'::uuid
order by source_name;

select rule_name, failed_row_count, detail, checked_at
from audit.data_quality_result
where batch_id = '<batch-id>'::uuid
order by rule_name;

select pipeline_name, last_successful_event_date, last_successful_batch_id, updated_at
from audit.ingestion_watermark;
```
