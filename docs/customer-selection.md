# 예시 고객 선정 쿼리

추천 시연에 사용할 합성 고객을 사례별로 선정하는 PostgreSQL 조회 쿼리입니다.
기존 4번 가족 결합 사례는 4-A 프리미엄 가족결합과 4-B 총액결합으로 나눕니다.
각 기본 쿼리는 독립적으로 실행하며 최대 10명의 `user_id`와 `name`을 반환합니다.

## 선정 기준과 실행 조건

| 사례 | 선정 기준 |
| --- | --- |
| 1. YouTube 사용과 혜택 불일치 | 최근 30일 YouTube 사용량 20GB 이상, 전체 사용량의 30% 이상, YouTube 서비스 미선택 |
| 2. 고사용량·저가 요금제 | 최근 30일 사용량 80GB 이상, 월정액 61,000원 이하, 기본 데이터 30GB 이하 |
| 3. 저사용량·고가 요금제 | 최근 30일 사용량 15GB 미만, 월정액 80,000원 이상 |
| 4-A. 프리미엄 가족결합 미가입 | 프리미엄 가족결합 조건을 충족하는 미결합 가족의 초이스 고객 중 베이스 후보 외 고가 회선 |
| 4-B. 총액결합 미가입 | 가족 구성원 2명 이상인 미결합 가족 중 정책표상 모바일 총액결합 할인액이 양수인 가족의 고객 |

- 사용량 기준은 예시 선정을 위한 값입니다. 각 쿼리의 `where` 조건과 `limit 10`을 조정할 수 있습니다.
- 사례 1~3은 최신 적재일을 종료일로 하는 최근 30일을 사용합니다. 30일 모두 관측된 고객만 포함하며, 사용량이 없는 날짜는 0으로 보충하지 않습니다.
- 사용량은 MB 합계를 1024로 나눈 GB입니다. YouTube 사용량은 시청시간이 아니라 `youtube_video`, `youtube_shorts`, `youtube_music`의 데이터 사용량입니다.
- 요금은 할인 전 월정액입니다. 현재 요금제·서비스·할인 상태를 조회하며 과거 상태를 재현하지 않습니다.
- 사례 1~3은 `ai_personalization` 조회 권한이 필요합니다. 사례 4-A와 4-B는 추가로 `dw_personalization` 조회 권한이 필요하며, 기본 `n8n_personalization` 역할에는 DW 직접 조회 권한이 없습니다.
- 사례 4의 정책 유효기간은 실행일(`current_date`) 기준입니다. 과거 정책을 검토할 때는 해당 표현식을 명시적인 기준일로 변경합니다.
- 가족 사례의 `limit 10`은 가족 10개가 아니라 고객 10명입니다. 같은 가족의 고객이 여러 행에 나올 수 있습니다.
- 이 문서는 수동 예시 선정용이며 [n8n 고정 쿼리 계약](integration/n8n-fixed-query-contract.md)의 등록 카탈로그에 추가된 쿼리는 아닙니다.
- 저장소 스키마와 정책 마스터를 기준으로 작성했습니다. 실제 DB 실행과 사례별 추출 건수는 아직 검증하지 않았습니다.

## SQL 파일 실행 방법

실행할 사례의 `.sql` 파일을 SQL 편집기에서 열어 해당 DB 연결로 실행합니다.
파일은 `tools/customer-selection/`에 있으며 사례별로 독립 실행합니다.
사용량·요금 기준과 고객 수를 바꿀 때는 SQL 파일을 수정합니다.

접속된 psql 프롬프트에서도 다음처럼 선택한 파일을 실행할 수 있습니다.
아래는 PowerShell 명령이 아니라 psql 명령이며, 저장소를 옮겼다면 경로를 수정합니다.

```psql
\i C:/kt_nd/tools/customer-selection/case_01_youtube_benefit_mismatch.sql
```

## 1. YouTube 사용량이 많지만 YouTube 혜택을 선택하지 않은 고객

현재 요금제에서 YouTube 혜택을 선택할 수 있지만 미선택한 고객과, 현재 요금제에
YouTube 혜택이 없는 고객을 `case_detail`로 구분합니다.
저장소 마스터에서는 `S002`가 `YouTube Premium Lite`입니다.

조회 SQL: [case_01_youtube_benefit_mismatch.sql](../tools/customer-selection/case_01_youtube_benefit_mismatch.sql)

### 초이스 미만의 7만~8만 원대 무제한 고객만 선정

사례 1 SQL 파일에서 마지막 `where`와 `order by` 사이에 있는 옵션 조건 다섯 줄의 주석을 해제합니다.
저장소 기준으로 `베이직80`은 월 80,000원 무제한이고, `초이스90`부터 YouTube 선택 혜택을 제공합니다.

서비스 미선택은 저장소에 기록된 요금제 혜택 선택 상태입니다. 외부에서 별도로 구매한
YouTube 구독 여부는 이 데이터로 판단하지 않습니다.

## 2. 데이터 사용량이 많지만 저가 요금제를 이용하는 고객

조회 SQL: [case_02_high_usage_low_fee.sql](../tools/customer-selection/case_02_high_usage_low_fee.sql)

`base_data_limit_gb`는 기본 제공량입니다. 연령별 추가 데이터와 이월량은 반영하지 않았으므로
실제 초과 사용 여부나 추가 요금 발생을 확정하는 쿼리는 아닙니다.

## 3. 데이터 사용량이 적지만 고가 요금제를 이용하는 고객

조회 SQL: [case_03_low_usage_high_fee.sql](../tools/customer-selection/case_03_low_usage_high_fee.sql)

요금제 하향 검토용 예시입니다. 사용량 외 부가서비스, 공유 데이터, 할인 등의 가치는 별도로 확인합니다.

## 4-A. 프리미엄 가족결합 할인을 받지 못하는 초이스 고객

저장소의 `D003` 정책은 추가 고가 회선에 대한 25% 할인입니다. 초이스 요금제 이용만으로
할인 자격이 결정되지 않으며, 현재 정책 마스터의 조건은 다음과 같습니다.

- 정상 이용 중인 KT 인터넷과 `BASIC_ESSENCE_PREMIUM` 인터넷 상품 그룹
- 월정액 77,000원 이상 모바일 회선 2개 이상
- 모바일 회선 10개 이하
- 베이스 회선 1개를 제외한 추가 고가 회선

가족 전체 고가 회선에서 베이스 후보를 먼저 선정하고, 나머지 회선 중 초이스 고객을 추출합니다.
베이스 후보 선정 순서는 생성기와 같은 월정액 오름차순 → 나이 내림차순 → 가입일 오름차순이며,
동률이면 `user_id`로 정렬합니다. 초이스 외 고가 회선도 가족의 자격과 베이스 후보 판단에 포함합니다.

조회 SQL: [case_04a_premium_family_not_enrolled.sql](../tools/customer-selection/case_04a_premium_family_not_enrolled.sql)

`potential_premium_discount_per_month`는 해당 고객을 추가 고가 회선으로 결합했을 때의
월 할인 후보 금액입니다. 베이스 회선 지정에 따라 대상이 달라질 수 있습니다.
청소년 추가 혜택(`D004`)은 이 사례의 선정 대상이 아닙니다.

## 4-B. 총액결합 할인을 받지 못하는 고객

미결합 가족의 모바일 월정액 합계, 인터넷 상품 그룹, 약정기간을 정책표에 대입합니다.
`D001` 모바일 총액결합 할인 풀이 0원보다 큰 가족의 고객을 추출합니다.

조회 SQL: [case_04b_total_bundle_not_enrolled.sql](../tools/customer-selection/case_04b_total_bundle_not_enrolled.sql)

`potential_family_mobile_discount`는 가족 전체 모바일 할인 풀입니다. 고객 행마다 표시되므로
이 컬럼을 고객별로 합산하면 같은 가족의 할인액이 중복됩니다. 개인별 금액은 균등·기여도 등
배분 방식에 따라 달라지며, 인터넷 회선 할인(`D005`)은 이 금액에 포함하지 않습니다.

4-A와 4-B에는 같은 가족이 나올 수 있습니다. 4-B의 금액은 가족의 참여 가능 모바일 전체를
합산한 일반 총액결합 시나리오입니다. 프리미엄 가족결합을 적용할 때는 베이스·저가 회선만
총액결합 계산에 포함하므로, 두 쿼리의 할인 후보 금액을 그대로 더하지 않습니다.

## 관련 기준 문서

- [개인화 뷰와 권한](../db/schema/060_ai_views_roles.sql)
- [개인화 DW 스키마](../db/schema/030_dw_personalization.sql)
- [원본 데이터 스키마와 할인 계산 기준](../generator/docs/data-schema.md)
- [합성 데이터 생성기](../generator/src/kt_synthetic_data_generator.py)
