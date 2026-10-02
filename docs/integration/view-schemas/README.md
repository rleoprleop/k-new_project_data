# AI 조회 뷰 스키마

운영·개인화 AI가 조회 뷰의 컬럼과 집계 기준을 이해할 수 있도록 관리하는 데이터 사전입니다. CSV의 한 행은 뷰의 컬럼 하나이며, 뷰 설명과 집계 기준은 해당 뷰의 모든 컬럼 행에 반복합니다.

| 영역 | 파일 | 뷰 수 | 컬럼 수 |
| --- | --- | ---: | ---: |
| 운영 | [operations-view-schema.csv](operations-view-schema.csv) | 10 | 58 |
| 개인화 | [personalization-view-schema.csv](personalization-view-schema.csv) | 12 | 87 |

기준은 저장소의 [AI 뷰 정의](../../../db/schema/060_ai_views_roles.sql)와 해당 DW·DM DDL 및 변환 SQL입니다. `max_age`의 NULL 의미에는 [연령 상한 마이그레이션](../../../db/schema/070_allow_open_ended_age_benefits.sql)을 반영합니다. 실제 배포 DB의 메타데이터를 조회한 결과는 아니므로 배포 변경이 있다면 적용된 SQL과 대조해야 합니다.

이 CSV는 실제 고객 행이나 생성 데이터를 포함하지 않는 관리용 스키마 명세이며, 쿼리 카탈로그처럼 Git에 포함합니다. UTF-8 인코딩, 쉼표 구분, 첫 행 헤더를 사용하며 모든 필드를 큰따옴표로 감쌉니다.

## CSV 필드

| 필드 | 의미 |
| --- | --- |
| `schema_name` | `ai_operations` 또는 `ai_personalization` |
| `view_name` | 스키마를 제외한 뷰 이름 |
| `view_description` | 뷰의 제공 정보 |
| `row_grain` | 한 행이 나타내는 업무·집계 단위 |
| `grain_columns` | 저장소 정의로 확인한 행 식별 컬럼을 `\|`로 구분. 뷰에 식별 컬럼이 모두 노출되지 않으면 빈 값 |
| `column_position` | SELECT 결과의 컬럼 순서. 1부터 시작 |
| `column_name` | 뷰가 반환하는 컬럼 이름 |
| `data_type` | 원천 DDL과 뷰 표현식에 따른 PostgreSQL 결과 타입 |
| `column_description` | 컬럼의 업무 의미 |
| `unit` | MB, GB, 원/월, 명, 건 등 의미상 단위. 적용할 단위가 없으면 빈 값 |
| `value_notes` | 날짜 표현, NULL 의미, 식별자 사용 등 해석 기준 |
| `source_expression` | AI 뷰의 SELECT 표현식. 별칭의 원천은 AI 뷰 정의에서 확인 |
| `join_notes` | 뷰를 연결할 때 사용할 키와 행 중복 주의사항 |
| `limitations` | 집계·현재 상태·누락 행·중복 등에 관한 제한 |
| `db_role` | 해당 영역 뷰에 SELECT 권한을 가진 reader 역할 |
| `query_ids` | 현재 쿼리 카탈로그에서 해당 뷰를 직접 참조하는 쿼리 ID를 `\|`로 구분. 직접 참조가 없으면 빈 값 |

`grain_columns`는 뷰에 선언된 PK 제약이 아니라 기반 테이블의 키와 뷰 조인·집계를 검토한 식별 기준입니다. `value_notes`의 NULL 설명 역시 원천 DDL과 업무 의미를 설명하며, PostgreSQL의 `information_schema.columns.is_nullable` 값을 기록한 것은 아닙니다.

## AI에 전달하는 방법

운영 AI에는 운영 스키마 CSV와 [운영 쿼리 카탈로그](../query-catalogs/operations-query-catalog.csv)를, 개인화 AI에는 개인화 스키마 CSV와 [개인화 쿼리 카탈로그](../query-catalogs/personalization-query-catalog.csv)를 함께 전달합니다. 스키마 CSV는 컬럼 이해용이며, 실행 가능한 쿼리와 parameter는 쿼리 카탈로그를 기준으로 합니다. [n8n 고정 쿼리 계약](../n8n-fixed-query-contract.md)에 따라 AI는 `query_id`와 등록된 parameter를 반환합니다.

뷰 컬럼과 쿼리 결과 컬럼은 다를 수 있습니다. 예를 들어 `PERS_002`는 뷰의 `total_usage_mb`를 `daily_usage_mb`로 반환하며, 쿼리에서 반올림하거나 계산한 결과도 뷰 타입·컬럼 자체와 구분해야 합니다.

월 컬럼 `calendar_month`는 `YYYY-MM-01`인 `date`입니다. 운영의 가명 고객 키와 개인화의 `user_id`는 직접 조인할 수 없습니다. 카테고리별 고유 사용자 수, 일별 월 누적값, 여러 서비스에 연결된 사용량을 합산할 때는 각 뷰의 `limitations`를 먼저 확인합니다.

## 갱신과 검증

뷰 정의, 기반 컬럼 타입, 마이그레이션, 집계 규칙 또는 쿼리 카탈로그를 변경하면 대응하는 CSV를 함께 갱신합니다.

1. 각 영역의 모든 AI 뷰가 CSV에 있는지 확인합니다.
2. SELECT 순서대로 컬럼 이름과 결과 타입을 대조합니다. `sum(numeric)`은 원천의 정밀도 제한을 유지하지 않는 `numeric`입니다.
3. 기반 테이블의 키, 조인, group by와 변환 SQL로 집계 기준·단위·NULL 의미를 확인합니다.
4. `query_ids`를 카탈로그의 `fixed_sql` 직접 참조와 대조합니다.
5. CSV를 다시 파싱해 행별 필드 수, 컬럼 순서 연속성, 중복 컬럼, 한글·쉼표·따옴표 보존을 확인합니다.

스키마 문서만 바꾸는 경우 CSV와 SQL의 대조 검증을 수행합니다. DB 스키마나 변환 규칙까지 바꾸는 경우에는 저장소 지침에 따른 파이프라인·품질 SQL 검증도 수행합니다.
