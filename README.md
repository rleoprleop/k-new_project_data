# 통신 데이터 기반 추천·운영 자동화 DB 파이프라인

이 프로젝트는 합성 통신 데이터를 생성하고 PostgreSQL의 임시 staging·DW·DM 계층으로 적재·가공하여, n8n 워크플로가 사용할 데이터베이스를 구축하는 시스템입니다.

데이터는 사용자별 요금제 추천을 위한 개인화 영역과 고객군·상품·콘텐츠 이용 현황을 위한 운영 영역으로 나눕니다. 각 영역의 Data Mart는 n8n에서 추천 및 운영 자동화 워크플로를 구성할 때 사용하는 데이터 기반이 됩니다.

## 데이터 흐름

```text
원본 CSV (로컬 Data Lake 또는 S3)
 스냅샷 CSV 13개 + 콘텐츠 사용량 CSV/날짜 파티션
              ↓
           pipeline
              ↓
PostgreSQL pg_temp.stg_*        배치 중 임시 적재·품질 검사
        ┌─────────────┴─────────────┐
dw_operations                dw_personalization
        ↓                             ↓
dm_operations                dm_personalization
운영 집계·지표                고객별 일/월 사용량·현재 상태
        ↓                             ↓
ai_operations                ai_personalization
        ↓                             ↓
n8n 운영 워크플로             n8n 요금제 추천 워크플로
```

- **Data Lake**: 개발 환경에서는 `generator/data/generated/`에 원본 CSV를 저장합니다.
- **임시 staging**: CSV를 `pg_temp.stg_*`에 적재하고 원본 품질을 검사합니다. 배치 트랜잭션이 끝나면 임시 테이블은 삭제됩니다.
- **DW / DM**: 운영과 개인화의 상세 데이터·집계·현재 상태를 별도 스키마로 관리합니다. 공통 상품·할인·정책 마스터도 두 DW에 각각 저장합니다.
- **AI View**: 각 n8n 계정은 해당 영역의 View를 고정 쿼리로 조회합니다. 최근 7일·30일과 추천 판단용 입력은 쿼리로 계산하고, AI가 조회 결과를 분석해 추천합니다.

로컬 실행은 생성 CSV를 직접 읽고, 현재 AWS 배포 경로는 한 Lambda에서 S3 파일을
다운로드한 뒤 같은 파이프라인으로 두 영역을 함께 처리합니다. 운영·개인화는
`content_usage_daily` 워터마크를 공유하며 n8n 워크플로와 조회 계정은 분리합니다.

## 디렉터리

| 경로 | 책임 |
| --- | --- |
| [`generator/`](generator/README.md) | 합성 원본 CSV 생성과 생성 결과 검증. 로컬 Data Lake를 만든다. |
| [`db/`](db/README.md) | 임시 staging·Audit·DW·DM·AI View의 DDL, 적재·변환·품질 SQL을 관리한다. |
| [`pipeline/`](pipeline/README.md) | DB SQL의 실행 순서, checksum·배치 ID·트랜잭션을 제어한다. |
| [`docs/`](docs/README.md) | 아키텍처, 데이터 사전, 기능 명세와 의사결정 문서를 관리한다. |
| [`deploy/lambda/`](deploy/lambda/README.md) | S3·Secrets Manager 연결과 Lambda 컨테이너 배포를 관리한다. |
| [`tools/verification/`](tools/verification/README.md) | 적재 후 실행 이력·워터마크·품질 결과를 읽기 전용으로 확인한다. |
| [`tools/customer-selection/`](docs/customer-selection.md) | 추천 시연용 사례 고객을 선정하는 조회 SQL을 관리한다. |

## 로컬 빠른 시작

1. `generator/`에서 합성 원본 CSV를 생성합니다.

   ```powershell
   cd generator
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python src/kt_synthetic_data_generator.py `
     --reference-date 2026-09-29 `
     --usage-through-date 2026-09-28 `
     --content-usage-layout single
   python scripts/check_distribution.py
   cd ..
   ```

2. PostgreSQL 15 이상과 `psql`을 준비한 뒤 저장소 루트에서 파이프라인을 실행합니다.

   ```powershell
   .\pipeline\scripts\run_pipeline.ps1 `
     -ConnectionString "postgresql://postgres:postgres@localhost:5432/kt_nd" `
     -ReferenceDate "2026-09-29" `
     -AllowSyntheticDefaultKey
   ```

위 빠른 시작은 단일 `content_usage.csv`를 사용하는 전체 파일 배치입니다. 대용량
콘텐츠를 날짜별로 생성·적재할 때는 `--content-usage-layout daily`로 생성한 뒤
증분 초기화와 일별 실행 경로를 사용합니다.

자세한 입력 데이터·스키마·실행 조건은 [`generator/README.md`](generator/README.md), [`db/README.md`](db/README.md), [`pipeline/SQL_EXECUTION.md`](pipeline/SQL_EXECUTION.md)를 참고합니다.

## Git 관리 원칙

가상환경, 생성 CSV, 로컬 아카이브(`generator/archive/`, `docs/archive/`)와 환경변수 파일은 Git에 올리지 않습니다. 소스 코드, SQL, 문서와 실행 스크립트를 추적하며, 고정 쿼리 명세인 `docs/query-catalogs/*.csv`와 과거 구현 SQL인 `db/legacy/`도 추적합니다. `db/legacy/`는 현재 파이프라인에서 실행하지 않습니다.
