# 목표 데이터 아키텍처

## 확정 범위

- 하나의 PostgreSQL DB 안에서 운영과 개인화를 별도 스키마로 분리합니다.
- S3의 14개 CSV가 원본이며 영구 Landing은 사용하지 않습니다.
- CSV는 배치 세션의 임시 staging에만 적재되고 트랜잭션 종료 시 삭제됩니다.
- 운영과 개인화는 별도 Lambda/실행 경로, 워터마크, n8n workflow, DB 계정을 사용합니다.
- 현재 요금제만 사용하며 요금제 이력 스냅샷은 만들지 않습니다.
- `subscription_start_date <= 기준일`을 가입자로 정의합니다. 취소는 없다고 가정합니다.
- 상세 사용량은 개인화만, category 사용량은 운영만 사용합니다.

## 흐름

```text
S3 CSV 14개
  ├─ 운영 실행: 원본 ID를 메모리/pg_temp에서 즉시 HMAC → dw_operations → dm_operations
  │                                                   → ai_operations → n8n_operations
  └─ 개인화 실행: user_id·name·detail 유지             → dw_personalization
                                                      → dm_personalization
                                                      → ai_personalization → n8n_personalization
```

## DW

두 DW 모두 `users`, `families`, `bundle_discount_compositions`, `plans`, `age_benefits`,
`plan_age_benefits`, `additional_services`, `plan_benefits`, `discounts`,
`internet_bundle_discount_rules`, `premium_family_discount_rules`, `user_discounts`,
`user_services`, `content_usage`의 14개 논리 테이블을 가집니다.

운영 DW는 이름을 저장하지 않고 연결 가능한 ID를 용도별 HMAC 키로 바꿉니다. 나이는
연령대로 바꾸고 사용량 detail은 category로 합산합니다. 개인화 DW는 `user_id`, `name`,
category와 detail을 유지합니다.

## DM과 조회 데이터

운영 DM에서는 현재 가입자 수, 일/월 사용량, 요금제·연령대·category 세그먼트, 가명 고객
사용량, 가족결합, 서비스, 할인을 조회할 수 있습니다.

개인화 DM에서는 고객 이름과 현재 요금제, 한 달의 일별 사용량, 일별 월 누적, 선택 일자의
category/detail, 월 category/detail, 선택 서비스 관련 detail, 최근 7일·30일, 가족·할인·서비스
상태를 조회할 수 있습니다.

Star Schema는 조인 경로와 grain을 고정해 쿼리를 단순하게 만들고 집계 테이블로 읽는 행 수를
줄입니다. 속도는 Star라는 이름 자체보다 정확한 grain, 인덱스, 일/월 사전 집계에서 나옵니다.
대용량 상세 행은 DW에 한 번만 저장하고 DM 상세 Fact는 View로 연결합니다.

## 이름 처리

`dm_personalization.dim_customer`와 개인화 AI View에 `user_id`, `name`을 함께 둡니다. 따라서
이름을 얻기 위한 별도 후속 쿼리는 필요 없습니다. 운영 AI View에는 이름과 원본 user_id가
없습니다.

## 추천 처리

추천 Feature 또는 추천 결과 테이블은 만들지 않습니다. 데이터베이스는 현재 요금제, 최근
7일·30일, 당월 사용량, category/detail, 선택 혜택과 후보 요금제 데이터를 반환합니다. AI가
고정 쿼리 결과를 분석해 추천합니다.

## 계정과 공개 RDS

- `n8n_operations`: `ai_operations` View만 SELECT
- `n8n_personalization`: `ai_personalization` View만 SELECT
- 두 계정 모두 DW/DM 기본 테이블과 쓰기 권한 없음
- 비밀번호는 n8n credential 또는 비밀 관리 도구에서 설정하고 저장소에 기록하지 않음
- RDS Security Group의 5432 인바운드는 n8n 고정 공인 IP `/32`만 허용
- `0.0.0.0/0` 금지, TLS 사용, 관리자 계정을 n8n에 사용하지 않음

Lambda가 고정 IP 없이 공개 RDS에 연결해야 하면 보안 그룹을 IP로 제한하기 어렵습니다.
이 경우 Lambda를 VPC에 두고 RDS 보안 그룹을 Lambda 보안 그룹에서만 허용하는 구성이
안전합니다.
