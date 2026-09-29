# Pipeline

이 폴더는 데이터 모델을 정의하지 않습니다. [`db/`](../db/README.md)의 Landing·DW·DM SQL을 정해진 순서와 하나의 배치 트랜잭션으로 실행하는 제어 계층입니다.

## 책임

- 원본 CSV 14개의 SHA-256을 계산해 입력 묶음을 식별한다.
- `audit.pipeline_run`에서 batch ID를 확보하고 재실행 상태를 관리한다.
- `db/schema → db/load → db/transform → db/quality` 순서로 SQL을 호출한다.
- 오류 시 해당 배치를 `FAILED` 상태로 기록한다.

## 구성

| 경로 | 역할 |
| --- | --- |
| [`scripts/run_pipeline.ps1`](scripts/run_pipeline.ps1) | 로컬 CSV 경로·연결 문자열·키를 받아 `psql`을 실행하는 진입점 |
| [`sql/010_run_pipeline.psql`](sql/010_run_pipeline.psql) | 스키마 초기화, 배치 트랜잭션, SQL 호출 순서와 재실행 삭제 순서 |
| [`scripts/initialize_incremental_pipeline.ps1`](scripts/initialize_incremental_pipeline.ps1) | 콘텐츠 사용량을 제외한 13개 현재 상태 CSV 초기화 |
| [`scripts/run_incremental_pipeline.ps1`](scripts/run_incremental_pipeline.ps1) | 일별 콘텐츠 파티션 catch-up 및 정정 실행 |
| [`sql/020_run_incremental_pipeline.psql`](sql/020_run_incremental_pipeline.psql) | 증분 트랜잭션, 워터마크, 영향 범위 재계산 |
| [`SQL_EXECUTION.md`](SQL_EXECUTION.md) | 실행 방법, 배치 이력과 검증 범위 |

기본 입력은 `generator/data/generated/`에 생성된 원본 CSV입니다. 로컬 실행 방법과 배치 동작은 [`SQL_EXECUTION.md`](SQL_EXECUTION.md)를 참고합니다.

`source_batch_id`는 실행 계보만 나타내며 DW/DM 업무 키에는 포함되지 않습니다.
전체 배치는 현재 상태를 전부 교체하고, 증분 배치는 사용 일자 파티션만 교체합니다.

## 실행 모드

| 모드 | 입력 | 실행 순서 |
| --- | --- | --- |
| 전체 파일 배치 | 최상위 스냅샷 CSV 13개와 단일 `content_usage.csv` | `run_pipeline.ps1` |
| 일별 파티션 배치 | 최상위 스냅샷 CSV 13개와 `raw/content_usage/event_date=.../part-*.csv` | `initialize_incremental_pipeline.ps1` 1회 → `run_incremental_pipeline.ps1` 반복 |

두 모드는 같은 DW/DM을 변경하므로 동일한 PostgreSQL advisory lock을 사용합니다.
`ReferenceDate`는 생성한 고객 스냅샷 기준일과 일치하도록 전체 배치와 증분 초기화
명령에 반드시 명시합니다.
