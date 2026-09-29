# Database

이 폴더는 PostgreSQL 데이터 계층의 단일 기준점입니다. 테이블·제약조건·적재·변환·품질 검사 SQL은 모두 이곳에서 관리하며, [`pipeline/`](../pipeline/README.md)은 이 SQL을 배치 순서대로 실행합니다.

## 논리 데이터 계층

```text
Data Lake (로컬 CSV 또는 향후 S3)
  → landing.raw_*                 원본 적재와 배치 이력
  → dw_common                     공통 마스터
  → dw_operations / dw_personalization
  → dm_operations / dm_personalization
```

| PostgreSQL 스키마 | 역할 |
| --- | --- |
| `audit` | 배치 상태, 파일 checksum·행 수, 품질 검사 결과 |
| `landing` | 원본 ID와 값이 유지되는 배치별 `raw_*` 테이블. Data Landing 계층 |
| `dw_common` | 요금제·할인·서비스·정책의 공통 기준 데이터 |
| `dw_operations` | 가명화된 운영 분석 상세 데이터 |
| `dw_personalization` | 사용자 연결이 가능한 개인화 상세 데이터와 identity bridge |
| `dm_operations` | 운영 지표·집계 Fact와 Dimension |
| `dm_personalization` | 사용자별 사용량 Fact와 추천 Feature Snapshot |

## 폴더와 실행 순서

| 경로 | 내용 |
| --- | --- |
| [`schema/`](schema/) | extension, audit, landing, DW, DM의 DDL |
| [`load/`](load/README.md) | CSV를 `landing.raw_*`에 적재하고 Raw 품질을 확인하는 SQL |
| [`transform/`](transform/) | Landing 데이터를 공통·운영·개인화 DW/DM으로 만드는 SQL |
| [`quality/`](quality/) | Landing·DW·DM 결과 검증 SQL |
| [`legacy/supabase-landing/`](legacy/supabase-landing/) | 가명화 분석 CSV를 직접 적재하던 이전 Supabase 초기안. 현재 파이프라인에서는 실행하지 않음 |

스키마를 준비한 뒤 `load → transform → quality` 순서로 실행합니다. 실제 트랜잭션 경계, 재실행, checksum과 오류 처리는 [`pipeline/SQL_EXECUTION.md`](../pipeline/SQL_EXECUTION.md)가 담당합니다.

운영·개인화 DW의 `family`는 Raw 가족 속성을 JSONB 대신 명시 컬럼으로 저장합니다. `dw_common`의 정책 JSONB와 개인화 DM의 `content_category_usage_ratio` JSONB는 그대로 유지합니다.

## 개발과 운영의 Lake

- **로컬 개발·PoC**: `generator/data/generated/*.csv`를 PostgreSQL `\copy`로 적재합니다.
- **AWS 운영 전환**: 같은 원본 CSV를 S3 Data Lake에 보관하고, 실행 환경이 S3에서 파일을 내려받아 동일한 Landing SQL을 수행합니다.

Landing 이후의 DW·DM SQL은 두 방식에서 공통으로 사용합니다.
