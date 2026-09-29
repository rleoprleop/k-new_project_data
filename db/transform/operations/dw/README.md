# 운영 DW

`dw_operations`는 원본 Raw(`landing.raw_*`)에서 운영 분석에 필요한 상세 데이터를 생성한다. 사용자·가족·결합 구성요소 ID는 도메인별 HMAC-SHA256 가명 키로 바꾸며, 이름과 원본 ID는 저장하지 않는다. 비개인정보 요금제·할인·서비스·정책 마스터는 `dw_common`에서 공유한다.

| 테이블 | 내용 | grain |
| --- | --- | --- |
| `family` | 가명 가족 키와 명시 컬럼으로 저장한 결합·인터넷 속성 | 배치 × 가족 |
| `customer` | 가명 사용자 키, 연령대, 가입 코호트·개월 수, 현재 요금제 | 배치 × 사용자 |
| `bundle_composition` | 가명 결합 구성요소, 상태와 시작·종료 월 | 배치 × 결합 구성요소 |
| `user_discount` | 할인 적용 관계와 시작·종료 월 | 배치 × 사용자 × 구성요소 × 할인 × 시작 월 |
| `user_service` | 선택 서비스와 시작 월 | 배치 × 사용자 × 서비스 × 혜택 유형 × 시작 월 |
| `content_usage` | 일별 콘텐츠 대·상세분류 사용량 | 배치 × 사용자 × 사용 일자 × 대·상세분류 |

| Raw 값 | 운영 DW 값 |
| --- | --- |
| `user_id`, `family_id`, `bundle_composition_id` | `AUSR_`, `AFAM_`, `ABND_` 접두사가 붙은 HMAC 키 |
| `name` | 저장하지 않음 |
| `age` | `8-12`, `13-18`, `19-24`, `25-34`, `35-49`, `50-64`, `65+` |
| `subscription_start_date` | 월 첫날인 `subscription_cohort`와 기준일 기준 `tenure_months` |
| 결합·할인·서비스 시작/종료일 | 월 첫날인 `start_month`, `end_month` |
| `content_usage.usage_date` | 일자 유지 |

가명 키는 `도메인:원본 ID`에 HMAC-SHA256을 적용한 결과의 앞 24자리 hex를 대문자로 표시한다. 같은 배치의 조인 키이며 익명 정보는 아니다.

`family`는 `source_batch_id`와 `analysis_family_key`를 별도 컬럼으로 유지한다. Raw의 나머지 속성인 `has_bundle`, `bundle_type`, `has_kt_internet`, `internet_product_group`, `internet_contract_months`, `internet_status`, `bundle_discount_method`, `total_discount_allocation_method`, `internet_benefit_discount_id`도 각각 같은 자료형의 컬럼으로 적재한다. `attributes` JSONB는 사용하지 않는다.

SQL은 [스키마](../../../schema/020_dw_operations.sql), [변환](010_build.sql), [검증](../../../quality/operations/dw/010_quality.sql)으로 나뉜다. 검증은 가족 9개 속성과 HMAC 가족 키·배치 ID의 Raw 대조, 사용량 합계, 운영 스키마의 `user_id`·`name` 컬럼 부재, 원본 사용자 ID와 가명 키의 불일치를 확인한다. 전체 실행 방법은 [SQL 실행](../../../../pipeline/SQL_EXECUTION.md)을 참고한다.
