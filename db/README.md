# 데이터베이스

원본 CSV를 운영 분석과 개인화 분석에 맞게 저장하고, 조회에 사용할 집계와 현재 상태를 만드는 PostgreSQL SQL을 관리합니다. PostgreSQL 15 이상을 사용합니다.

이 폴더는 처리 내용을 정의하고, [파이프라인](../pipeline/README.md)은 SQL의 실행 순서와 배치를 제어합니다.

## 데이터를 읽는 순서

```text
원본 CSV
  → 임시 staging: CSV를 읽고 원본 관계·값 검사
  → DW: 운영·개인화 목적에 맞는 상세 데이터 저장
  → DM: 고객 현재 상태와 일별·월별 집계 구성
  → AI View: n8n 계정이 조회할 데이터 공개
```

staging은 작업 중에만 존재하는 임시 적재 공간입니다. DW(Data Warehouse)는 상세 데이터를 보관하고, DM(Data Mart)은 질문에 바로 사용할 집계와 상태를 제공합니다. AI View는 허용된 조회 범위를 고정합니다.

## 스키마별 역할

| 스키마 | 저장하거나 제공하는 내용 |
| --- | --- |
| `audit` | 배치 상태, 원본 파일 checksum·행 수, 워터마크, 품질 검사 결과 |
| `pg_temp` | 세션의 `stg_*` 임시 테이블. 배치 트랜잭션 종료 시 삭제 |
| `dw_operations` | 이름을 제외하고 연결 키를 가명화한 운영 상세 데이터 |
| `dw_personalization` | 원본 사용자 ID·이름과 콘텐츠 detail을 유지한 개인화 상세 데이터 |
| `dm_operations` | 가입자·가족결합·서비스·할인 현황과 운영 사용량 집계 |
| `dm_personalization` | 고객 현재 상태, 고객별 일·월 사용량과 월 detail 집계 |
| `ai_operations` | 운영 n8n 고정 쿼리가 조회하는 View |
| `ai_personalization` | 개인화 n8n 고정 쿼리가 조회하는 View |

공통 상품·할인·정책 마스터는 두 DW에 각각 저장합니다. `transform/common/010_load_master.sql`은 공통 적재 코드를 의미하며 별도의 `dw_common` 스키마를 만들지 않습니다.

## 운영과 개인화의 차이

두 DW는 원본의 14개 논리 테이블을 각각 가집니다. 업무 목적에 따라 사용자 정보와 콘텐츠 사용량을 다르게 저장합니다.

| 구분 | 운영 | 개인화 |
| --- | --- | --- |
| 사용자·가족·결합·고객 서비스·고객 할인 연결 키 | 용도별 HMAC-SHA256 가명 키 | 원본 업무 키 유지 |
| 이름 | 제외 | `user_id`와 함께 저장·조회 |
| 나이 | 연령대 | 원본 나이 |
| 콘텐츠 상세 | detail을 category로 합산 | category와 제한적 detail 유지 |
| 사용량 한 행의 단위 | 가명 사용자 × 일자 × category | 사용자 × 일자 × category × detail |
| n8n 조회 계정 | `n8n_operations` | `n8n_personalization` |

두 계정은 해당 `ai_*` View와 같은 영역 DW의 공개 마스터 8개를 SELECT할 수 있습니다.
공개 마스터는 `plans`, `age_benefits`, `plan_age_benefits`, `additional_services`,
`plan_benefits`, `discounts`, `internet_bundle_discount_rules`, `premium_family_discount_rules`입니다.
고객·가족·사용량 DW와 DM 기본 객체는 직접 조회할 수 없으며 DW/DM 쓰기 권한도 없습니다.
현재 요금제만 관리하고 변경 이력 스냅샷은 만들지 않습니다. 가입자는
`subscription_start_date <= 기준일`로 판단하고, 사용량은 가입일 당일부터 적재합니다.

## DM에서 조회할 수 있는 것

DM은 Dimension(고객·요금제·날짜 등의 기준 정보)과 사용량·현재 상태를 연결하는 Star Schema로 구성됩니다.

### 운영 DM

- 전체·요금제·연령대별 가입자 현황
- 일별·월별 총사용량과 요금제 × 연령대 × category 사용량
- 가명 고객별 일 사용량과 월 category 사용량
- 가족결합·KT 인터넷 현황, 선택 서비스와 할인 분포

주요 Dimension은 `dim_date`, `dim_plan`, `dim_age_band`, `dim_content_category`, `dim_analysis_customer`, `dim_analysis_family`, `dim_service`, `dim_discount`입니다. 사용량 테이블은 `daily_usage_segment`, `monthly_usage_segment`, `customer_daily_usage`, `customer_monthly_category_usage`입니다.

### 개인화 DM

| 객체 | 제공하는 데이터 |
| --- | --- |
| `dim_customer` | `user_id`, `name`과 고객 현재 상태 |
| `customer_daily_usage` | 하루 총사용량과 월 누적 사용량 |
| `customer_content_daily_usage` | 선택 일자의 category/detail 상세 조회 View |
| `customer_monthly_usage` | 월 총사용량과 일평균 |
| `customer_monthly_content_usage` | 월 category/detail 사용량 |
| `customer_service_current` | 현재 선택 서비스 |
| `customer_discount_current` | 현재 할인 |
| `customer_family_current` | 가족결합과 인터넷 상태 |
| `bridge_service_content` | 선택 서비스와 관련 detail의 연결 |

대용량 상세 사용량은 DW에 한 번 저장하고, 일별 상세 DM은 View로 연결합니다. 일 합계와 월 합계·월 detail은 물리 테이블입니다. 최근 7일·30일 사용량은 고정 쿼리가 일별 집계에서 계산하며 추천 Feature Snapshot이나 추천 결과 테이블을 만들지 않습니다.

## 폴더와 파일

| 경로 | 역할 |
| --- | --- |
| `schema/` | Audit·DW·DM·AI View·역할 DDL과 번호별 마이그레이션 |
| `load/` | 임시 테이블 생성과 CSV `\copy` 적재 |
| `transform/common/` | 개인정보가 없는 정책·상품 마스터를 두 DW에 적재 |
| `transform/operations/{dw,dm}/` | 운영 상세 변환과 집계 |
| `transform/personalization/{dw,dm}/` | 개인화 상세 변환과 집계 |
| `quality/` | 원본 staging과 각 DW/DM의 품질 검사 |

각 도메인의 변환 SQL과 대응하는 품질 SQL은 같은 계층 구성을 따릅니다. `010`은 전체 구성, `020`은 콘텐츠 사용량 증분/정정을 처리합니다. 객체명에 `fact_` 접두사는 사용하지 않습니다.

적재 파일은 다음 역할로 나뉩니다.

| 파일 | 역할 |
| --- | --- |
| [001_create_staging.sql](load/001_create_staging.sql) | 14개 임시 테이블 생성 |
| [005_load_master_staging.psql](load/005_load_master_staging.psql) | 사용량을 제외한 스냅샷 13개와 감사 메타데이터 적재 |
| [010_load_full_staging.psql](load/010_load_full_staging.psql) | 단일 콘텐츠 파일을 포함한 전체 CSV 14개 적재 |
| [020_load_incremental_content_usage.psql](load/020_load_incremental_content_usage.psql) | 날짜 파티션 사용량과 manifest 적재 |

실행기는 CSV 폴더의 절대 경로를 `input_csv_directory`로 전달합니다. 적재 SQL은 `\cd`로 클라이언트 작업 폴더를 지정한 뒤 고정 파일명을 `\copy`에 사용합니다. `\copy` 자체는 psql 변수를 치환하지 않으며, `\ir` 참조는 해당 SQL 파일의 위치를 기준으로 해석합니다.

## 타입과 마이그레이션에서 주의할 점

`age_benefits.max_age`의 NULL은 나이 상한이 없다는 뜻입니다. `min_age`는 필수이며 상한이 있으면 `max_age >= min_age`여야 합니다. staging과 두 DW는 NULL을 보존합니다.

[070_allow_open_ended_age_benefits.sql](schema/070_allow_open_ended_age_benefits.sql)은 두 DW의 `max_age`에서 NOT NULL 제약만 제거합니다. 행 삭제·데이터 변환·타입 변경은 없으며 재실행할 수 있습니다. 모든 파이프라인 진입점이 적용하고, 적재 트랜잭션 전에 커밋하므로 이후 적재 실패에도 스키마 변경은 남습니다.

프리미엄 가족결합의 `enrollment_min_age`, `enrollment_max_age`, `benefit_end_age`는 원본에 `18.0`처럼 정수의 소수 표기가 있을 수 있습니다. staging은 정밀도 제한 없는 `numeric`으로 읽고 `staging_premium_family_age_integer` 검사 후 두 DW의 `integer`로 변환합니다. NULL은 유지하며 실제 소수 값, integer 범위 초과, NaN·무한대는 거절합니다. 임시 타입만 바꾸는 경우 영구 스키마 마이그레이션은 필요하지 않습니다.

이미 실행된 영구 스키마의 변경은 새 번호 SQL로 추가하고 재실행 가능하게 작성합니다. 기존 데이터가 있는 DB를 마이그레이션하려고 증분 초기화를 실행하면 안 됩니다.

### 공개 마스터 직접 조회 권한

[080_grant_public_master_read.sql](schema/080_grant_public_master_read.sql)은 각 DW 스키마의
`USAGE`와 위 8개 테이블의 `SELECT`만 해당 조회 역할에 부여합니다. 기존 역할 연결을 통해
`n8n_operations`와 `n8n_personalization`에도 적용됩니다. 데이터·타입·기존 View는 변경하지
않으며 재실행할 수 있습니다. 테이블 전체 또는 미래 테이블에 대한 포괄 권한은 부여하지 않습니다.

전체·초기화·증분 파이프라인에서 `060`의 역할 생성과 `070` 이후 적용합니다. 적재 트랜잭션
전에 커밋하므로 이후 적재가 실패해도 권한 변경은 남습니다. 기존 DB에서는 전체 파이프라인을
재실행하지 않고, 관리자 또는 권한 부여가 가능한 객체 소유자의 psql 세션에서 실행합니다.

```psql
\set ON_ERROR_STOP on
\i C:/kt_nd/db/schema/080_grant_public_master_read.sql
```

권한을 되돌리려면 같은 8개 테이블의 `SELECT`와 해당 DW 스키마의 `USAGE`를 해당 조회 역할에서
`revoke`합니다. `080`이 다음 파이프라인 실행 때 다시 적용되므로 지속적으로 되돌리려면 실행 경로도
함께 변경해야 합니다. 다른 경로로 부여된 권한은 별도로 확인합니다.

[030_reader_permissions.sql](quality/030_reader_permissions.sql)은 세 파이프라인의 배치 품질 검사에서
두 역할과 두 LOGIN의 마스터 조회, 허용 목록 밖 객체 조회 제한, DW/DM 쓰기 제한을 확인합니다.

### 운영 고객·월 선집계 뷰 적용

[130_install_operations_monthly_preagg_view.sql](schema/130_install_operations_monthly_preagg_view.sql)은
실험한 `ai_operations.v_customer_monthly_usage_filtered_preagg`를 영구 뷰로 추가합니다.
숫자 고객·월 키로 카테고리 사용량을 합산한 뒤 고객·날짜 차원을 조인하고,
기간 조건을 집계 전에 적용하도록 `month_key`도 노출합니다.
`sum(numeric)` 결과는 정밀도 제한 없는 numeric이며 원본 숫자 고객 키는 공개하지 않습니다.

060의 스키마·역할과 기초 DM이 준비된 DB에서 객체 소유자/관리자가 직접 적용합니다.
스키마 파일을 기존 트랜잭션이 없는 관리자 psql 세션에서 적용합니다.

```psql
\set ON_ERROR_STOP on
begin;
\i C:/kt_nd/db/schema/130_install_operations_monthly_preagg_view.sql
commit;
```

130은 재실행 가능하고 기존 카테고리 뷰·테이블·데이터·인덱스를 변경하지 않습니다.
조회 권한은 role_operations_reader에 부여해 기존 역할 연결의 n8n_operations가 사용합니다.
뷰 소유자 권한으로 기초 DM을 읽으므로 운영 조회 계정에 DM 직접 SELECT를 추가하지 않습니다.
일반 뷰이므로 사용량 증분·정정 후 현재 DM을 조회할 때 합산하며 REFRESH나 추가 적재 로직이 없습니다.

전체·증분 초기화·증분/정정의 세 파이프라인 SQL이 060·070·080 이후 130을 적용합니다.
Lambda 초기화·증분·정정도 같은 경로를 사용하므로 새 DB 구성에 뷰·권한이 포함됩니다.
다른 스키마 DDL처럼 배치 적재 트랜잭션 전에 커밋돼 이후 적재 실패에도 뷰·권한은 남습니다.
기존 DB에는 초기화·전체 적재를 다시 실행하지 않고 위 스키마 파일만 적용합니다.
운영 카탈로그 002·005와 뷰 스키마 CSV에도 정의를 반영했으며,
외부 n8n의 카탈로그 입력은 변경된 CSV로 갱신해야 합니다.

측정은 n8n_operations로 직접 접속해
[운영 계정 측정 파일](../tools/query-plans/compare_operations_reader_preagg.psql)을 실행합니다.
같은 데이터·64MB·custom plan 조건에서 이전 SQL과 현재 카탈로그 SQL을 비교합니다.
상세 실행계획은 [계획 확인 파일](../tools/query-plans/explain_operations_preagg.psql)로 비교합니다.
사용 방법은 [비교 도구 안내](../tools/query-plans/README.md)에 정리했습니다.

대응 품질 SQL은 [030_monthly_preagg_quality.sql](quality/operations/ai/030_monthly_preagg_quality.sql)입니다.
관리자용 별도 읽기 전용 검사로 컬럼 계약·고객/월 중복·월 총합·조회 권한·월 첫날 키를 확인합니다.
이 전체 데이터 대조는 성능 측정·스키마 적용에 자동 포함하지 않습니다.
배치의 030_reader_permissions.sql에는 새 뷰의 운영 역할/LOGIN 조회 권한과
네 컬럼 계약 검사를 추가했습니다. 해당 검사도 이번 작업에서 실행하지 않았습니다.
130을 되돌릴 때는 카탈로그 002·005와 n8n 등록 SQL을 먼저 이전 본문으로 복원한 뒤,
관리자 세션에서 해당 새 뷰만 DROP VIEW합니다. 지속적으로 제거하려면 세 파이프라인의
130 참조도 함께 되돌려야 하며, 참조를 유지하면 다음 파이프라인 실행에서 다시 생성됩니다.

## 실행과 검증

개별 변환 SQL은 배치 변수와 staging에 의존하므로 [파이프라인 실행기](../pipeline/README.md)를 사용합니다. 원본 품질 검사 후 두 DW/DM을 처리하고 최종 품질 검사를 수행합니다.

성공은 요청한 `audit.pipeline_run`의 `SUCCEEDED` 상태, 기록된 품질 검사 결과, 필요한 경우 워터마크를 함께 확인합니다. 품질 실패 시 검사 기록도 롤백될 수 있어 실패 행이 없다는 사실만으로 성공을 판단하지 않습니다. [도구 안내](../tools/README.md)에 확인 방법이 있습니다.

## 관련 문서

- [전체 설계와 데이터 흐름](../docs/architecture.md)
- [원본 데이터 사전과 정책 규칙](../docs/data/raw-data-schema.md)
- [파이프라인 날짜·재실행 규칙](../pipeline/README.md)
- [n8n 조회 계약](../docs/integration/n8n-fixed-query-contract.md)
