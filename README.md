# 통신 데이터 기반 추천·운영 자동화 DB 파이프라인

이 프로젝트는 합성 통신 데이터를 생성하고 PostgreSQL의 Landing·DW·DM 계층으로 적재·가공하여, n8n 워크플로가 사용할 데이터베이스를 구축하는 시스템입니다.

데이터는 사용자별 요금제 추천을 위한 개인화 영역과 고객군·상품·콘텐츠 이용 현황을 위한 운영 영역으로 나눕니다. 각 영역의 Data Mart는 n8n에서 추천 및 운영 자동화 워크플로를 구성할 때 사용하는 데이터 기반이 됩니다.

## 데이터 흐름

```text
로컬 Data Lake
 generator/data/generated/*.csv
              ↓
           pipeline
              ↓
PostgreSQL landing.raw_*       원본 CSV의 배치별 적재·품질 검사
              ↓
dw_common                      공통 상품·할인·정책 마스터
        ┌─────────────┴─────────────┐
dw_operations                dw_personalization
        ↓                             ↓
dm_operations                dm_personalization
운영 집계·지표                사용자별 Fact·추천 Feature
        ↓                             ↓
n8n 운영 워크플로             n8n 요금제 추천 워크플로
```

- **Data Lake**: 개발 환경에서는 `generator/data/generated/`에 원본 CSV를 저장합니다.
- **Data Landing**: `landing.raw_*`는 Lake의 CSV를 PostgreSQL에서 처리할 수 있게 배치 단위로 적재한 첫 계층입니다.
- **DW / DM**: 목적별 상세 데이터와 즉시 사용할 집계·Feature를 분리합니다.

운영 환경에서는 원본 CSV 저장소를 S3 Data Lake로 전환할 수 있습니다.

## 디렉터리

| 경로 | 책임 |
| --- | --- |
| [`generator/`](generator/README.md) | 합성 원본 CSV 생성과 생성 결과 검증. 로컬 Data Lake를 만든다. |
| [`db/`](db/README.md) | Landing·Audit·DW·DM의 DDL, 적재·변환·품질 SQL을 관리하는 단일 기준점. |
| [`pipeline/`](pipeline/README.md) | DB SQL의 실행 순서, checksum·배치 ID·트랜잭션을 제어한다. |
| [`docs/`](docs/README.md) | 아키텍처, 데이터 사전, 기능 명세와 의사결정 문서를 관리한다. |

## 로컬 빠른 시작

1. `generator/`에서 합성 원본 CSV를 생성합니다.

   ```powershell
   cd generator
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python src/kt_synthetic_data_generator.py
   python scripts/check_distribution.py
   cd ..
   ```

2. PostgreSQL 15 이상과 `psql`을 준비한 뒤 저장소 루트에서 파이프라인을 실행합니다.

   ```powershell
   .\pipeline\scripts\run_pipeline.ps1 `
     -ConnectionString "postgresql://postgres:postgres@localhost:5432/kt_nd" `
     -AllowSyntheticDefaultKey
   ```

자세한 입력 데이터·스키마·실행 조건은 [`generator/README.md`](generator/README.md), [`db/README.md`](db/README.md), [`pipeline/SQL_EXECUTION.md`](pipeline/SQL_EXECUTION.md)를 참고합니다.

## Git 관리 원칙

가상환경, 재생성 가능한 CSV, 레거시 아카이브와 환경변수 파일은 Git에 올리지 않습니다. 소스 코드, SQL, 문서와 실행 스크립트만 추적합니다.
