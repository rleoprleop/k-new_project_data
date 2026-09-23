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
| [`SQL_EXECUTION.md`](SQL_EXECUTION.md) | 실행 방법, 배치 이력과 검증 범위 |

기본 입력은 `generator/data/generated/`에 생성된 원본 CSV입니다. 로컬 실행 방법과 배치 동작은 [`SQL_EXECUTION.md`](SQL_EXECUTION.md)를 참고합니다.
