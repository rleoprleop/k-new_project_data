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

## 감사 조회

```sql
select batch_id, source_set_checksum, reference_date, status, started_at, ended_at, error_message
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
```
