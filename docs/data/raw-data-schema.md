# KT 합성 원본 데이터 스키마

이 문서는 `generator/data/generated/`에 생성되는 원본 성격의 합성 CSV 관계, 컬럼, enum, Null 의미와 사용 방법을 설명한다. 가명화된 `generator/data/generated_analysis/`는 컬럼과 날짜 정밀도가 다르므로 [분석용 데이터 스키마](analysis-data-schema.md)를 참고한다. 데이터 생성 기준·합성 가중치는 [생성 상세 사양](generation-spec.md), 실행 및 검증 방법은 [생성기 README](../../generator/README.md)를 참고한다.

## 1. 이 데이터 모델을 읽는 순서

처음 데이터를 사용할 때는 아래 순서로 이해하면 쉽다.

1. `users`에서 분석할 사용자를 선택한다.
2. `users.current_plan_id`로 `plans`를 조회하면 현재 모바일 요금제를 알 수 있다.
3. `users.family_id`가 있으면 같은 `family_id`를 가진 사용자가 한 가족이다.
4. `families`에서 그 가족의 인터넷 보유 여부, 인터넷 할인 그룹, 결합 종류와 계산 방식을 확인한다.
5. `bundle_discount_compositions`에서 결합에 참여한 인터넷·모바일 회선과 각 회선의 역할을 확인한다.
6. `user_discounts`와 `discounts`를 조인하면 각 모바일 사용자가 현재 받는 할인 혜택 종류를 확인할 수 있다.
7. 실제 정책 금액이나 자격 조건은 `internet_bundle_discount_rules`와 `premium_family_discount_rules`에서 조회한다.
8. 사용량 기반 추천에는 `content_usage`, 요금제 부가 혜택 비교에는 `plan_benefits`와 `user_services`를 사용한다.

논리적 관계는 다음과 같다.

```text
users ── current_plan_id ───────────────> plans
  │                                           │
  │ family_id                                 ├── plan_age_benefits ──> age_benefits
  │                                           └── plan_benefits ──────> additional_services
  v
families ── family_id ──> bundle_discount_compositions
  │                              │
  │ internet_benefit_discount_id │ bundle_composition_id
  v                              v
discounts <────────────── user_discounts ──> users
  │
  ├── internet_bundle_discount_rules
  └── premium_family_discount_rules

users ──> user_services ──> additional_services
users ──> content_usage
```

### 관계와 카디널리티

`1:0..N`은 부모 한 행에 자식이 없거나 여러 행일 수 있다는 뜻이다. N쪽 테이블을 조인하면 부모 행이 여러 번 나타날 수 있으므로, 사용자·가족 수나 금액을 집계할 때는 먼저 필요한 grain으로 집계한 뒤 조인한다.

| 부모 테이블 | 자식 테이블 | 관계 | 조인 키 | 사용 시 주의점 |
|---|---|---|---|---|
| `plans` | `users` | 1:0..N | `plans.plan_id = users.current_plan_id` | 요금제별 사용자가 여러 명이다. |
| `families` | `users` | 1:0..N | `families.family_id = users.family_id` | 독립 사용자는 `users.family_id=Null`이다. |
| `families` | `bundle_discount_compositions` | 1:0..N | `family_id` | 결합 가족은 인터넷 1행과 모바일 여러 행을 가질 수 있다. |
| `users` | `bundle_discount_compositions` | 1:0..1 | `user_id` | 모바일 구성요소만 사용자와 연결되고 인터넷 구성요소의 `user_id`는 Null이다. |
| `plans` | `plan_age_benefits` | 1:0..N | `plan_id` | 연령 혜택별로 요금제 행이 반복된다. |
| `age_benefits` | `plan_age_benefits` | 1:0..N | `age_benefit_id` | `(plan_id, age_benefit_id)` 조합은 유일하다. |
| `plans` | `plan_benefits` | 1:0..N | `plan_id` | 선택 후보·고정 혜택 수만큼 요금제가 반복된다. |
| `additional_services` | `plan_benefits` | 1:0..N | `service_id` | 하나의 서비스가 여러 요금제에 제공될 수 있다. |
| `users` | `user_services` | 1:0..N | `user_id` | 초이스 더블 사용자는 복수 선택 행을 가질 수 있다. |
| `additional_services` | `user_services` | 1:0..N | `service_id` | 실제 선택 사용자 수만큼 서비스가 반복된다. |
| `users` | `user_discounts` | 1:0..N | `user_id` | 한 사용자가 결합 할인과 추가 할인을 함께 받을 수 있다. |
| `bundle_discount_compositions` | `user_discounts` | 1:0..N | `bundle_composition_id` | 모바일 구성요소의 적용 혜택만 연결된다. |
| `discounts` | `user_discounts` | 1:0..N | `discount_id` | 적용 여부이며 할인금액 자체는 아니다. |
| `discounts` | `internet_bundle_discount_rules` | 1:0..N | `discount_id` | 조건 구간별 정책 행이 여러 개다. |
| `discounts` | `premium_family_discount_rules` | 1:0..N | `discount_id` | 현재 `D003`, `D004` 규칙이 저장된다. |
| `users` | `content_usage` | 1:0..N | `user_id` | 날짜·상세분류별 행이므로 조인 전 목적에 맞게 집계한다. |

`content_usage.content_detail`과 `additional_services.service_id`의 연결은 물리 FK가 아니다. [3.14절의 의미 매핑](#314-content_usagecsv)을 분석 규칙으로 적용한다.

### 키와 Null을 읽는 방법

- `PK`: 테이블에서 행 하나를 유일하게 식별하는 기본키다.
- `FK`: 다른 테이블의 PK를 참조하는 외래키다.
- `Null 허용`: 데이터 누락이 아니라 해당 속성이 적용되지 않는 정상 상태일 수 있다.
- 날짜는 `YYYY-MM-DD`, 금액은 별도 표기가 없으면 부가세 포함 월 원화 금액, 데이터량은 GB 또는 MB 단위다.
- `end_date=Null`은 현재 종료일이 정해지지 않은 활성 상태를 뜻한다.
- 정책 구간의 최대값이 `Null`이면 상한이 없고, 최소·최대값이 모두 `Null`이면 그 구간축을 사용하지 않는다는 뜻이다.

## 2. 현재 생성 데이터 스냅샷

이 절의 건수는 현재 `generator/data/generated`에 저장된 CSV를 직접 읽어 확인한 결과다. 다시 생성하면 건수와 분포는 달라질 수 있지만 스키마와 값의 의미는 유지된다.

| 테이블 | 행 수 | 의미 |
|---|---:|---|
| `users` | 1,000 | 모바일 사용자 |
| `families` | 227 | 가족 그룹 |
| `bundle_discount_compositions` | 445 | 결합에 참여한 인터넷·모바일 구성요소 |
| `plans` | 24 | 모바일 요금제 마스터 |
| `age_benefits` | 4 | 연령 혜택 마스터 |
| `plan_age_benefits` | 94 | 요금제별 연령 혜택 값 |
| `additional_services` | 9 | 선택·고정 부가서비스 마스터 |
| `plan_benefits` | 33 | 요금제와 부가서비스의 제공 관계 |
| `discounts` | 5 | 할인 식별자 마스터 |
| `internet_bundle_discount_rules` | 99 | 총액·정액·인터넷 할인 구간 규칙 |
| `premium_family_discount_rules` | 2 | 프리미엄 25%·청소년 할인 규칙 |
| `user_discounts` | 316 | 실제 사용자 할인 혜택 적용 행 |
| `user_services` | 166 | 실제 사용자가 선택한 부가서비스 |
| `content_usage` | 1,348,999 | 1,000명 × 90일 × 사용자별 활성 상세분류 사용량 |

현재 사용자는 8~88세이며, 가족 소속 사용자는 560명, 독립 사용자는 440명이다. 콘텐츠 사용 기간은 2026-06-17부터 2026-09-14까지다.

현재 주요 결합 분포는 다음과 같다.

| 항목 | 값 | 가족 수 |
|---|---|---:|
| 결합 종류 | `INTERNET_MOBILE` | 119 |
| 결합 종류 | `PREMIUM_FAMILY` | 9 |
| 결합 미가입 | `bundle_type=Null` | 99 |
| 인터넷 그룹 | `BASIC_ESSENCE_PREMIUM` | 140 |
| 인터넷 그룹 | `SLIM` | 38 |
| 인터넷 없음 | `internet_product_group=Null` | 49 |
| 결합 계산 | `TOTAL` | 84 |
| 결합 계산 | `FIXED` | 44 |

기본키 중복, 필수 기본키 Null, 주요 외래키 고아 행을 포함한 30개 무결성 검사를 모두 통과했다.

## 3. 상세 데이터 사전

### 3.1 `users.csv`

사용자 한 명의 최소 신상 정보와 현재 모바일 요금제, 가족 연결 키를 저장한다. 요금제 가격과 속성은 중복 저장하지 않고 `plans`에서 조회한다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `user_id` | 문자열 | 불가 | PK | 사용자 식별자. 예: `U00001` |
| `name` | 문자열 | 불가 |  | 합성 사용자 이름 |
| `age` | 정수 | 불가 |  | 기준일 현재 만 나이 |
| `gender` | enum | 불가 |  | 성별 코드. 아래 enum 참고 |
| `subscription_start_date` | 날짜 | 불가 |  | 현재 모바일 가입 시작일 |
| `current_plan_id` | 문자열 | 불가 | FK → `plans.plan_id` | 현재 이용 중인 모바일 요금제 |
| `family_id` | 문자열 | 허용 | FK → `families.family_id` | 가족 그룹. Null이면 데이터상 연결된 가족이 없는 독립 사용자 |

`gender` enum:

| 값 | 의미 |
|---|---|
| `F` | 여성 |
| `M` | 남성 |

### 3.2 `families.csv`

가족 구성 자체와 가족 단위 인터넷·결합 상태를 저장한다. 가족 구성원 수는 별도 컬럼으로 저장하지 않고 `users`를 집계한다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `family_id` | 문자열 | 불가 | PK | 가족 식별자 |
| `has_bundle` | boolean | 불가 |  | 현재 인터넷-모바일 결합에 가입했으면 `True` |
| `bundle_type` | enum | 허용 |  | 가입한 결합 종류. 미가입이면 Null |
| `has_kt_internet` | boolean | 불가 |  | KT 인터넷 계약을 보유하면 `True`. 정지 상태도 계약 보유에 포함 |
| `internet_product_group` | enum | 허용 |  | 상세 인터넷 상품 대신 할인표를 선택하기 위한 그룹. 인터넷이 없으면 Null |
| `internet_contract_months` | enum 정수 | 허용 |  | 인터넷 약정기간. 인터넷이 없으면 Null |
| `internet_status` | enum | 불가 |  | 인터넷 회선의 현재 상태 |
| `bundle_discount_method` | enum | 허용 |  | 모바일 할인 계산 방식. 결합 미가입이면 Null |
| `total_discount_allocation_method` | enum | 허용 |  | `TOTAL` 모바일 할인 풀의 사용자별 배분 방식. `FIXED` 또는 미가입이면 Null |
| `internet_benefit_discount_id` | 문자열 | 허용 | FK → `discounts.discount_id` | 가족 인터넷 회선에 적용되는 혜택. 현재 결합 가족은 `D005`, 미가입은 Null |

`bundle_type` enum:

| 값 | 의미 |
|---|---|
| `INTERNET_MOBILE` | 일반 인터넷-모바일 결합. 모든 모바일 회선을 총액 또는 정액 방식으로 계산 |
| `PREMIUM_FAMILY` | 프리미엄 가족결합. 베이스 회선과 저가 회선은 총액/정액, 추가 고가 회선은 25% 방식 적용 |
| Null | 인터넷-모바일 결합 미가입 |

`internet_product_group` enum:

| 값 | 의미 |
|---|---|
| `BASIC_ESSENCE_PREMIUM` | 베이직·에센스·프리미엄 계열을 대표하는 높은 할인표 그룹. 프리미엄 가족결합 가능 그룹 |
| `SLIM` | 슬림 계열을 대표하는 낮은 할인표 그룹. 이 데이터에서는 일반 인터넷-모바일 결합만 가능 |
| Null | KT 인터넷 계약 없음 |

`internet_contract_months` enum:

| 값 | 의미 |
|---:|---|
| `12` | 1년 약정. 정책 기준 할인액의 1/4 적용 |
| `24` | 2년 약정. 정책 기준 할인액의 1/2 적용 |
| `36` | 3년 약정. 정책 기준 할인액 전액 적용 |

`internet_status` enum:

| 값 | 의미 |
|---|---|
| `ACTIVE` | 정상 이용 중. 결합 가입 가능 |
| `SUSPENDED` | 계약은 있으나 정지 상태. 현재 결합 할인 미적용 |
| `NONE` | KT 인터넷 계약 없음 |

`bundle_discount_method` enum:

| 값 | 의미 |
|---|---|
| `TOTAL` | 결합 대상 모바일 월정액 합계 구간으로 할인 풀을 계산 |
| `FIXED` | 각 모바일 회선의 월정액 구간별 고정 할인액을 계산 |
| Null | 결합 미가입 |

`total_discount_allocation_method` enum:

| 값 | 의미 |
|---|---|
| `EQUAL` | 총액결합 모바일 할인 풀을 대상 회선 수로 균등 배분 |
| `CONTRIBUTION` | 각 회선 월정액이 총액에서 차지하는 비율로 배분 |
| Null | `FIXED` 방식이거나 결합 미가입 |

주요 상태 규칙:

- `has_bundle=True`이면 `internet_status=ACTIVE`, `bundle_type`, `bundle_discount_method`, `internet_benefit_discount_id=D005`가 존재한다.
- `bundle_discount_method=TOTAL`일 때만 `total_discount_allocation_method`가 존재한다.
- `bundle_type=PREMIUM_FAMILY`이면 `internet_product_group=BASIC_ESSENCE_PREMIUM`이다.
- `has_kt_internet=False`이면 `internet_status=NONE`이고 인터넷 그룹·약정기간은 Null이다.

### 3.3 `bundle_discount_compositions.csv`

결합에 실제로 포함된 인터넷 회선과 모바일 회선을 기록한다. 결합 가족마다 인터넷 구성요소 1행과 참여 모바일 사용자별 1행이 생성된다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `bundle_composition_id` | 문자열 | 불가 | PK | 결합 구성요소 식별자 |
| `family_id` | 문자열 | 불가 | FK → `families.family_id` | 구성요소가 속한 가족 |
| `component_type` | enum | 불가 |  | 인터넷 또는 모바일 구분 |
| `user_id` | 문자열 | 조건부 허용 | FK → `users.user_id` | 모바일 구성요소의 사용자. 인터넷 구성요소는 Null |
| `component_role` | enum | 불가 |  | 결합 계산에서의 구성요소 역할 |
| `status` | enum | 불가 |  | 현재 구성요소 상태. 현재 생성값은 `ACTIVE`만 존재 |
| `start_date` | 날짜 | 불가 |  | 결합 참여 시작일 |
| `end_date` | 날짜 | 허용 |  | 종료일. 현재 활성 행은 Null |

`component_type` enum:

| 값 | 의미 |
|---|---|
| `INTERNET` | 가족의 베이스 인터넷 회선 |
| `MOBILE` | 가족 구성원의 모바일 회선 |

`component_role` enum:

| 값 | 적용 대상 | 의미 |
|---|---|---|
| `BASE_INTERNET` | 인터넷 | 결합 기준 인터넷 회선. `user_id`는 Null |
| `BASE_MOBILE` | 모바일 | 결합의 대표 모바일 회선. 프리미엄 가족결합에서는 월정액 77,000원 이상 |
| `PREMIUM_MOBILE` | 모바일 | 프리미엄 가족결합의 베이스 외 77,000원 이상 회선. `D003` 25% 대상 |
| `LOW_MOBILE` | 모바일 | 베이스·프리미엄 추가 회선이 아닌 참여 모바일 회선. 일반결합에서는 베이스 외 모바일을 이 역할로 표현 |

### 3.4 `plans.csv`

모바일 요금제의 가격, 데이터·음성·문자 제공량, 부가 혜택 등 추천 계산의 기준 속성을 저장한다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `plan_id` | 문자열 | 불가 | PK | 요금제 식별자 |
| `plan_name` | 문자열 | 불가 |  | 표시용 요금제명 |
| `plan_family` | enum | 불가 |  | 요금제 계열. ID 접두어와 대응 |
| `plan_category` | enum 문자열 | 불가 |  | 한글 표시용 분류 |
| `monthly_fee` | 정수 | 불가 |  | 할인 전 월정액(원) |
| `data_limit_gb` | 실수 | 허용 |  | 기본 데이터 제공량. 무제한 요금제는 Null |
| `is_unlimited` | boolean | 불가 |  | 기본 데이터가 무제한이면 `True` |
| `throttle_speed` | enum 문자열 | 허용 |  | 기본 제공량 소진 후 속도. 해당 조건이 없거나 별도 정의되지 않으면 Null |
| `voice` | enum 문자열 | 불가 |  | 음성 제공 조건 |
| `sms` | enum 문자열 | 불가 |  | 문자 제공 조건 |
| `base_shared_data_gb` | 실수 | 불가 |  | 공유·테더링 등에 사용할 기준 데이터량 |
| `is_rollover` | boolean | 불가 |  | 미사용 데이터 이월 여부 |
| `membership_tier` | enum | 허용 |  | 멤버십 등급. 제공하지 않으면 Null |
| `choice_tier` | enum | 허용 |  | 초이스 혜택 등급. 초이스 계열이 아니면 Null |
| `network_type` | enum | 불가 |  | 가입 가능한 망 유형. 청소년 5G 할인 판정에도 사용 |
| `device_discount_lines` | 정수 | 불가 |  | 스마트기기 할인 가능 회선 수 |
| `data_sharing_discount_lines` | 정수 | 불가 |  | 데이터쉐어링 할인 가능 회선 수 |
| `family_bundle_eligible` | boolean | 불가 |  | 가족결합 대상 가능 여부. 현재 24개 요금제는 모두 `True` |

`plan_family` enum:

| 값 | 의미 | 현재 ID 계열 |
|---|---|---|
| `VOICE` | 소량 데이터·정량 음성 중심 | `P10xx` |
| `BASIC_ROLLOVER` | 데이터 이월형 베이직 | `P21xx` |
| `BASIC` | 일반 베이직 | `P22xx` |
| `CHOICE` | 선택형 구독 혜택을 제공하는 초이스 | `P30xx` |
| `CHOICE_DOUBLE` | 선택 혜택 2개를 제공하는 초이스 더블 | `P40xx` |

주요 enum:

| 컬럼 | 가능한 값 | 의미 |
|---|---|---|
| `plan_category` | `통합 음성`, `베이직(이월)`, `베이직`, `초이스`, `초이스 더블` | 사용자에게 보여주는 요금제 분류명 |
| `throttle_speed` | `400Kbps`, `1Mbps`, `5Mbps`, Null | 기본량 소진 후 최대 속도 또는 미적용 |
| `voice` | `100분`, `180분`, `기본제공` | 월 음성 제공 조건 |
| `sms` | `100건`, `180건`, `기본제공` | 월 문자 제공 조건 |
| `membership_tier` | `VIP`, `VVIP`, Null | 멤버십 등급 또는 미제공 |
| `choice_tier` | `BASIC`, `SPECIAL`, `PREMIUM`, `DOUBLE`, Null | 초이스 혜택 단계 또는 미적용 |
| `network_type` | `LTE_OR_5G`, `5G` | LTE/5G 공용 또는 5G 전용 |

### 3.5 `age_benefits.csv`

나이만으로 적용 가능한 혜택 구간을 정의한다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `age_benefit_id` | 문자열 | 불가 | PK | 연령 혜택 식별자 |
| `benefit_name` | enum 문자열 | 불가 |  | 혜택명: `스쿨덤`, `Y덤`, `65+덤`, `75+덤` |
| `min_age` | 정수 | 불가 |  | 적용 최소 만 나이, 포함 |
| `max_age` | 정수 | 허용 |  | 적용 최대 만 나이, 포함. Null이면 상한 없음 |
| `includes_safety_box` | boolean | 불가 |  | 안심박스 성격의 보호 혜택 포함 여부 |

현재 구간:

| ID | 혜택 | 연령 | 안심박스 |
|---|---|---|---|
| `AB10` | 스쿨덤 | 8~18세 | 포함 |
| `AB20` | Y덤 | 19~34세 | 미포함 |
| `AB30` | 65+덤 | 65~74세 | 포함 |
| `AB40` | 75+덤 | 75세 이상 | 포함 |

### 3.6 `plan_age_benefits.csv`

요금제와 연령 혜택의 조합별 실제 추가 제공량을 저장한다. 같은 연령 혜택이라도 요금제에 따라 값이 다르므로 매핑 테이블이 필요하다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `plan_age_benefit_id` | 문자열 | 불가 | PK | 요금제-연령혜택 매핑 식별자 |
| `plan_id` | 문자열 | 불가 | FK → `plans.plan_id` | 대상 요금제 |
| `age_benefit_id` | 문자열 | 불가 | FK → `age_benefits.age_benefit_id` | 대상 연령 혜택 |
| `bonus_data_gb` | 실수 | 불가 |  | 추가 일반 데이터 GB. `0`이면 추가 없음 |
| `bonus_shared_data_gb` | 실수 | 불가 |  | 추가 공유 데이터 GB |
| `bonus_voice_minutes` | 실수 | 불가 |  | 추가 음성 통화 분 |
| `bonus_sms_count` | 실수 | 불가 |  | 추가 문자 건수 |
| `bonus_video_minutes` | 실수 | 불가 |  | 추가 영상통화 분 |

`plan_id + age_benefit_id` 조합은 중복되지 않는다.

### 3.7 `additional_services.csv`

요금제에서 선택하거나 고정으로 제공할 수 있는 서비스의 기준 정보를 저장한다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `service_id` | 문자열 | 불가 | PK | 서비스 식별자 |
| `service_name` | 문자열 | 불가 |  | 서비스 표시명 |
| `service_category` | enum | 불가 |  | 서비스 분석 분류 |
| `normal_monthly_price` | 정수 | 불가 |  | 요금제 혜택 없이 별도 이용할 때의 월 기준 가격. `0`은 별도 비교가격을 두지 않음 |

`service_category` enum:

| 값 | 의미 |
|---|---|
| `video` | 영상 스트리밍 서비스 |
| `video_music` | 영상·음악 결합 성격 서비스 |
| `music` | 음악 서비스 |
| `ebook` | 전자책·독서 서비스 |
| `device` | 스마트기기 또는 데이터쉐어링 회선 혜택 |
| `device_insurance` | 단말 보험·멤버십 성격 혜택 |
| `ai` | AI·클라우드 성격 서비스 |

### 3.8 `plan_benefits.csv`

어떤 요금제가 어떤 서비스를 어떤 방식으로 제공하는지 정의한다. 이 테이블은 선택 가능한 후보이고, 사용자의 실제 선택은 `user_services`에 저장한다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `plan_benefit_id` | 문자열 | 불가 | PK | 요금제 혜택 매핑 식별자 |
| `plan_id` | 문자열 | 불가 | FK → `plans.plan_id` | 혜택 제공 요금제 |
| `service_id` | 문자열 | 불가 | FK → `additional_services.service_id` | 제공 서비스 |
| `benefit_type` | enum | 불가 |  | 혜택 제공 방식 |
| `benefit_value` | 문자열 | 불가 |  | `택1`, `택2`, 회선 할인 등 사람이 읽는 제공 조건 |
| `is_selectable` | boolean | 불가 |  | 사용자가 후보 중 선택하는 혜택이면 `True` |
| `option_group` | enum | 허용 |  | 선택 후보 묶음. 고정 혜택은 Null |
| `selection_count` | 정수 | 불가 |  | 해당 그룹에서 선택 가능한 개수. 고정 혜택은 `0` |

`benefit_type` enum:

| 값 | 의미 |
|---|---|
| `CHOICE` | 기본 초이스 후보 중 1개 선택 |
| `PLUS` | 상위 초이스 요금제에서 추가로 제공하는 선택 후보 |
| `DOUBLE_CHOICE` | 초이스 더블 후보 중 2개 선택 |
| `DEVICE` | 스마트기기·데이터쉐어링 관련 고정 혜택 |
| `INSURANCE` | 단말 보험·멤버십 관련 고정 혜택 |

`option_group` enum:

| 값 | 의미 |
|---|---|
| `PRIMARY_CHOICE` | 기본 초이스 선택 묶음 |
| `PLUS_CHOICE` | 추가 플러스 선택 묶음 |
| `DOUBLE_CHOICE` | 초이스 더블 선택 묶음 |
| Null | 사용자가 선택하지 않는 고정 혜택 |

### 3.9 `discounts.csv`

할인 이름과 정책 영역을 통일하는 공통 코드 테이블이다. 금액은 여기에 저장하지 않고 할인별 정책 테이블에서 조회한다.

| ID | `policy_domain` | `benefit_code` | 의미 |
|---|---|---|---|
| `D001` | `INTERNET_BUNDLE` | `TOTAL_MOBILE_POOL` | 총액결합에서 모바일 회선들에 배분하는 할인 풀 |
| `D002` | `INTERNET_BUNDLE` | `FIXED_MOBILE_LINE` | 정액결합에서 개별 모바일 회선에 적용하는 고정 할인 |
| `D003` | `PREMIUM_FAMILY` | `ADDITIONAL_HIGH_25PCT` | 프리미엄 가족결합의 베이스 외 고가 회선 25% 혜택 |
| `D004` | `PREMIUM_FAMILY` | `YOUTH_5G` | 조건을 충족한 청소년 회선의 추가 고정 할인 |
| `D005` | `INTERNET_BUNDLE` | `INTERNET_COMPONENT` | 가족 인터넷 회선에 적용되는 결합 혜택 |

`policy_domain` enum:

| 값 | 의미 |
|---|---|
| `INTERNET_BUNDLE` | 인터넷-모바일 결합 정책에서 금액을 조회 |
| `PREMIUM_FAMILY` | 프리미엄 가족결합 조건·금액을 조회 |

### 3.10 `internet_bundle_discount_rules.csv`

총액결합, 정액결합, 인터넷 할인 금액을 조건 구간별로 저장한 정책표다. 한 행은 하나의 약정기간·인터넷 그룹·금액 구간에 대응한다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `internet_bundle_rule_id` | 문자열 | 불가 | PK | 정책 규칙 식별자 |
| `discount_id` | 문자열 | 불가 | FK → `discounts.discount_id` | `D001`, `D002`, `D005` 중 하나 |
| `bundle_discount_method` | enum | 불가 |  | `TOTAL` 또는 `FIXED` |
| `rule_type` | enum | 불가 |  | 어떤 금액을 계산하는 규칙인지 표시 |
| `internet_product_group` | enum | 불가 |  | 적용 인터넷 그룹. `ANY`는 그룹 무관 |
| `contract_months` | enum 정수 | 불가 |  | `12`, `24`, `36`개월 |
| `mobile_total_fee_min` | 실수 | 허용 |  | 가족 모바일 월정액 합계의 포함 최소값 |
| `mobile_total_fee_max` | 실수 | 허용 |  | 가족 모바일 월정액 합계의 포함 최대값. Null이면 상한 없음 |
| `mobile_line_fee_min` | 실수 | 허용 |  | 개별 모바일 월정액의 포함 최소값 |
| `mobile_line_fee_max` | 실수 | 허용 |  | 개별 모바일 월정액의 포함 최대값. Null이면 상한 없음 |
| `discount_target` | enum | 불가 |  | 할인 귀속 대상 |
| `allocation_method` | enum | 불가 |  | 정책상 가능한 배분 방법 |
| `discount_amount` | 실수 | 불가 |  | 조건을 충족할 때의 월 할인 기준금액(원) |
| `discount_rate` | 실수 | 허용 |  | 비율 규칙용 예약 컬럼. 현재 99행 모두 Null |
| `effective_start_date` | 날짜 | 허용 |  | 정책 적용 시작일 예약 컬럼. 현재 모두 Null |
| `effective_end_date` | 날짜 | 허용 |  | 정책 적용 종료일 예약 컬럼. 현재 모두 Null |

`rule_type` enum:

| 값 | 할인 ID | 의미 |
|---|---|---|
| `MOBILE_TOTAL_POOL` | `D001` | 모바일 월정액 합계 구간으로 계산한 모바일 할인 풀 |
| `MOBILE_LINE` | `D002` | 개별 모바일 월정액 구간별 정액 할인 |
| `INTERNET_BASE` | `D005` | 총액/정액 정책의 기본 인터넷 할인 부분 |
| `INTERNET_ADDITIONAL` | `D005` | 인터넷 그룹에 따른 추가 인터넷 할인 부분 |

`internet_product_group` enum:

| 값 | 의미 |
|---|---|
| `BASIC_ESSENCE_PREMIUM` | 높은 인터넷 할인표 그룹 |
| `SLIM` | 낮은 인터넷 할인표 그룹 |
| `ANY` | 인터넷 그룹과 무관한 규칙 |

`discount_target` enum:

| 값 | 의미 |
|---|---|
| `MOBILE_POOL` | 여러 모바일 회선에 배분할 총 할인 풀 |
| `MOBILE_LINE` | 개별 모바일 회선 |
| `BASE_INTERNET` | 베이스 인터넷 회선 또는 정책상 선택된 베이스 모바일 |
| `INTERNET_ADDITIONAL` | 인터넷 회선 추가 할인 |

`allocation_method` enum:

| 값 | 의미 |
|---|---|
| `EQUAL_OR_CONTRIBUTION` | 가족이 균등 또는 월정액 기여도 배분을 선택할 수 있음 |
| `BASE_MOBILE_OR_INTERNET_SPLIT` | 정책상 베이스 모바일과 인터넷 중 할인 귀속 위치를 선택할 수 있음 |
| `NOT_APPLICABLE` | 별도 배분이 필요 없는 고정 대상 할인 |

구간 경계는 최소·최대를 모두 포함한다. 예를 들어 `mobile_total_fee_min=64900`, `mobile_total_fee_max=108899`는 64,900원 이상 108,899원 이하를 뜻한다.

### 3.11 `premium_family_discount_rules.csv`

프리미엄 가족결합의 사용자 자격과 할인 방식을 저장한다. 현재 행은 `D003`과 `D004` 두 개다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `premium_family_rule_id` | 문자열 | 불가 | PK | 프리미엄 규칙 식별자 |
| `discount_id` | 문자열 | 불가 | FK → `discounts.discount_id` | `D003` 또는 `D004` |
| `benefit_type` | enum | 불가 |  | 규칙 종류 |
| `eligible_component_role` | enum | 불가 |  | 정책상 대상 역할 |
| `requires_internet` | boolean | 불가 |  | 인터넷 결합 필수 여부 |
| `minimum_high_line_count` | 정수 | 불가 |  | 가족 내 고가 모바일 최소 회선 수 |
| `maximum_mobile_line_count` | 정수 | 불가 |  | 결합 가능한 최대 모바일 회선 수 |
| `minimum_plan_fee` | 실수 | 불가 |  | 혜택 대상 사용자의 최소 모바일 월정액 |
| `required_network_type` | enum | 불가 |  | 대상 사용자에게 필요한 망 유형 |
| `guardian_minimum_plan_fee` | 실수 | 허용 |  | 법정대리인 최소 월정액. 법정대리인이 필요 없으면 Null |
| `guardian_required_network_type` | enum | 불가 |  | 법정대리인 회선 망 조건 |
| `enrollment_min_age` | 실수 | 허용 |  | 가입 가능한 최소 나이. 나이 조건이 없으면 Null |
| `enrollment_max_age` | 실수 | 허용 |  | 가입 가능한 최대 나이, 포함 |
| `benefit_end_age` | 실수 | 허용 |  | 이 나이에 도달하면 혜택 종료. 해당 없으면 Null |
| `requires_legal_guardian` | boolean | 불가 |  | 적격 법정대리인 회선 필요 여부 |
| `discount_rate` | 실수 | 허용 |  | 비율 할인. 고정액 규칙이면 Null |
| `discount_amount` | 실수 | 허용 |  | 고정 할인액. 비율 규칙이면 Null |
| `effective_start_date` | 날짜 | 허용 |  | 정책 적용 시작일 예약 컬럼. 현재 Null |
| `effective_end_date` | 날짜 | 허용 |  | 정책 적용 종료일 예약 컬럼. 현재 Null |

정책 enum과 현재 두 규칙:

| 할인 | `benefit_type` | `eligible_component_role` | 핵심 조건 | 혜택 |
|---|---|---|---|---|
| `D003` | `ADDITIONAL_HIGH_25PCT` | `PREMIUM_MOBILE` | 인터넷 필수, 77,000원 이상 회선 2개 이상, 최대 10회선 | 베이스 외 고가 회선 월정액의 25% |
| `D004` | `YOUTH_5G` | `HIGH_MOBILE` | 본인·법정대리인 모두 80,000원 이상 5G, 만 18세 이하 가입, 만 20세 도달 시 종료 | 월 5,500원 |

`eligible_component_role=HIGH_MOBILE`은 청소년 규칙의 정책 개념이다. `bundle_discount_compositions.component_role`의 실제 저장 enum은 아니며, 실제 구성 행은 상황에 따라 `BASE_MOBILE` 또는 `PREMIUM_MOBILE`일 수 있다.

`required_network_type`과 `guardian_required_network_type` enum:

| 값 | 의미 |
|---|---|
| `ANY` | 망 유형 제한 없음 |
| `5G` | `plans.network_type=5G` 필요 |

### 3.12 `user_discounts.csv`

사용자에게 실제로 적용 중인 모바일 할인 혜택을 저장한다. 금액을 저장하지 않으므로 정책 변경이나 후보 요금제 분석 시 정책표로 다시 계산할 수 있다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `user_discount_id` | 문자열 | 불가 | PK | 사용자 할인 적용 식별자 |
| `user_id` | 문자열 | 불가 | FK → `users.user_id` | 할인 수혜 사용자 |
| `bundle_composition_id` | 문자열 | 불가 | FK → `bundle_discount_compositions.bundle_composition_id` | 할인 대상 모바일 구성요소 |
| `discount_id` | enum FK | 불가 | FK → `discounts.discount_id` | 적용 혜택. 현재 `D001`~`D004` |
| `status` | enum | 불가 |  | 현재 생성값은 `ACTIVE` |
| `start_date` | 날짜 | 불가 |  | 할인 적용 시작일 |
| `end_date` | 날짜 | 허용 |  | 할인 종료일. 활성 혜택은 Null |

`discount_id`별 사용자 행의 의미:

| 값 | 의미 |
|---|---|
| `D001` | 이 사용자가 총액결합 모바일 할인 풀 배분 대상임 |
| `D002` | 이 사용자가 정액결합 회선 할인 대상임 |
| `D003` | 이 사용자가 프리미엄 추가 고가 회선 25% 대상임 |
| `D004` | 이 사용자가 청소년 추가 할인 대상임 |

`D005`는 가족 인터넷 회선에 한 번 적용되므로 `user_discounts`에 저장하지 않는다. `families.internet_benefit_discount_id`에서 확인한다.

### 3.13 `user_services.csv`

초이스 계열 요금제 가입자가 실제로 선택한 서비스를 저장한다. 요금제가 제공할 수 있는 전체 후보는 `plan_benefits`에 있다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `user_service_id` | 문자열 | 불가 | PK | 사용자 서비스 선택 식별자 |
| `user_id` | 문자열 | 불가 | FK → `users.user_id` | 서비스를 선택한 사용자 |
| `service_id` | 문자열 | 불가 | FK → `additional_services.service_id` | 실제 선택 서비스 |
| `benefit_type` | enum | 불가 |  | 선택 출처: `CHOICE`, `PLUS`, `DOUBLE_CHOICE` |
| `start_date` | 날짜 | 불가 |  | 서비스 선택 적용 시작일 |

`benefit_type` enum:

| 값 | 의미 |
|---|---|
| `CHOICE` | 기본 초이스 묶음에서 선택 |
| `PLUS` | 상위 요금제의 추가 선택 묶음에서 선택 |
| `DOUBLE_CHOICE` | 초이스 더블 묶음에서 선택 |

`DEVICE`, `INSURANCE`는 사용자 선택 행이 아니라 요금제 고정 혜택이므로 `plan_benefits`에서 직접 조회한다.

### 3.14 `content_usage.csv`

사용자별 일간 데이터 사용량을 대분류와 제한적 상세분류로 분해한다. 상세분류는 초이스 추천에 필요한 서비스 수준까지만 포함하고 서비스 ID, 검색어, 영상·음악 제목은 저장하지 않는다. 사용자별 활성 상세분류 수가 다르므로 전체 행 수는 가변적이다.

| 컬럼 | 논리 타입 | Null | 키 | 설명 |
|---|---|---|---|---|
| `content_usage_id` | 문자열 | 불가 | PK | 사용량 행 식별자. 계산 의미가 없는 인덱스 |
| `user_id` | 문자열 | 불가 | FK → `users.user_id` | 사용 사용자 |
| `usage_date` | 날짜 | 불가 |  | 사용 일자 |
| `content_category` | enum | 불가 | 복합 grain | 개인정보 최소화를 위한 콘텐츠 대분류 |
| `content_detail` | enum | 불가 | 복합 grain | 초이스 추천용 제한적 상세분류 |
| `data_usage_mb` | 실수 | 불가 |  | 해당 날짜·유형에서 사용한 데이터 MB. `0` 가능 |

`content_category` enum:

| 값 | 의미 |
|---|---|
| `video` | 장편 영상·OTT |
| `short_form` | 숏폼 영상 |
| `music` | 음악 스트리밍 |
| `ai` | AI 검색·도우미 |
| `ebook` | 전자책 |
| `web` | 웹 탐색·일반 브라우징 |
| `sns` | 소셜 네트워크 |
| `messaging` | 메신저 |
| `game` | 온라인 게임 |
| `video_call` | 영상통화 |
| `navigation` | 지도·내비게이션 |
| `cloud` | 클라우드 업로드·다운로드 |
| `other` | 위 분류에 포함되지 않는 기타 사용량 |

`content_detail` enum과 상위 대분류:

| `content_category` | `content_detail` |
|---|---|
| `video` | `netflix`, `youtube_video`, `tving`, `disney_plus`, `other_video` |
| `short_form` | `youtube_shorts`, `other_short_form` |
| `music` | `youtube_music`, `genie_music`, `other_music` |
| `ai` | `google_ai`, `other_ai` |
| `ebook` | `milli_ebook`, `other_ebook` |
| `web` | `general_web` |
| `sns` | `general_sns` |
| `messaging` | `general_messaging` |
| `game` | `general_game` |
| `video_call` | `general_video_call` |
| `navigation` | `general_navigation` |
| `cloud` | `general_cloud` |
| `other` | `other` |

행의 논리 grain은 `(user_id, usage_date, content_category, content_detail)`이다. `user_id`만 물리 FK이며, `content_detail`은 개인정보 최소화를 위해 서비스 ID를 저장하지 않는 분석 코드다.

초이스 관련 상세분류와 서비스 마스터의 관계는 다음과 같다. 이 관계는 물리 FK가 아니라 분석 시 사용하는 의미 매핑이다.

| `content_detail` | 관련 `additional_services` | 관계 |
|---|---|---|
| `netflix` | S001 Netflix | 의미 매핑 |
| `youtube_video`, `youtube_shorts`, `youtube_music` | S002 YouTube Premium | 의미 매핑 |
| `tving` | S003 티빙 | 의미 매핑 |
| `genie_music` | S004 지니뮤직 | 의미 매핑 |
| `milli_ebook` | S005 밀리의서재 | 의미 매핑 |
| `disney_plus` | S006 Disney+ | 의미 매핑 |
| `google_ai` | S009 Google AI | 의미 매핑 |
| `other_*`, `general_*`, `other` | 없음 | 특정 초이스 서비스와 연결하지 않음 |

선택 혜택 사용 여부를 비교할 때는 `content_usage.user_id = user_services.user_id`로 사용자를 연결한 뒤 위 의미 매핑을 적용한다. 생성 확률과 가중치는 [생성 상세 사양](generation-spec.md)를 참고한다.

## 4. 자주 사용하는 조인 예시

아래 예시는 ANSI SQL 형태다. CSV를 데이터베이스에 적재하거나 pandas 조인으로 옮겨 사용할 수 있다.

### 4.1 사용자와 현재 요금제 조회

```sql
SELECT
    u.user_id,
    u.name,
    p.plan_name,
    p.monthly_fee,
    p.data_limit_gb,
    p.is_unlimited
FROM users u
JOIN plans p
  ON p.plan_id = u.current_plan_id;
```

### 4.2 한 사용자의 가족 구성원 전체 조회

```sql
SELECT family_member.*
FROM users target
JOIN users family_member
  ON family_member.family_id = target.family_id
WHERE target.user_id = :user_id
  AND target.family_id IS NOT NULL;
```

`family_relationships`가 없어도 이 조인으로 같은 가족 구성원 목록과 인원수는 만들 수 있다. 다만 `family_id`만으로 부모·자녀 같은 정확한 관계는 복원할 수 없다. 현재 적용된 청소년 할인은 `user_discounts`의 `D004`로 확인할 수 있지만, 후보 요금제로 바꾼 뒤 법정대리인 조건까지 다시 판정하려면 별도 관계 데이터 또는 “가족 내 조건 충족 성인을 법정대리인으로 간주”하는 분석 가정이 필요하다.

### 4.3 사용자가 현재 받는 모바일 할인 종류 조회

```sql
SELECT
    u.user_id,
    u.name,
    d.discount_id,
    d.discount_name,
    c.component_role,
    ud.start_date
FROM users u
JOIN user_discounts ud
  ON ud.user_id = u.user_id
JOIN discounts d
  ON d.discount_id = ud.discount_id
JOIN bundle_discount_compositions c
  ON c.bundle_composition_id = ud.bundle_composition_id
WHERE u.user_id = :user_id
  AND ud.status = 'ACTIVE';
```

이 결과는 혜택 종류를 보여주며 할인금액은 보여주지 않는다. 금액은 할인 ID에 따라 두 정책표에서 계산한다.

### 4.4 사용자를 통해 가족 인터넷 혜택 확인

```sql
SELECT
    u.user_id,
    f.family_id,
    f.internet_product_group,
    f.internet_contract_months,
    f.bundle_discount_method,
    f.internet_benefit_discount_id
FROM users u
JOIN families f
  ON f.family_id = u.family_id
WHERE u.user_id = :user_id;
```

가족 구성원은 모두 같은 `D005`를 조회할 수 있지만, D005가 각 사용자에게 반복 적용되는 것은 아니다. 가족 인터넷 회선 한 개에 한 번만 적용한다.

### 4.5 가족 모바일 월정액 합계 만들기

일반 `INTERNET_MOBILE` 결합은 가족의 참여 모바일 전부를 합산한다. `PREMIUM_FAMILY`는 `BASE_MOBILE`과 `LOW_MOBILE`만 합산하고 `D003` 대상 `PREMIUM_MOBILE`은 제외한다.

```sql
SELECT
    c.family_id,
    SUM(p.monthly_fee) AS mobile_total_fee
FROM bundle_discount_compositions c
JOIN users u
  ON u.user_id = c.user_id
JOIN plans p
  ON p.plan_id = u.current_plan_id
JOIN families f
  ON f.family_id = c.family_id
WHERE c.component_type = 'MOBILE'
  AND (
       f.bundle_type = 'INTERNET_MOBILE'
       OR c.component_role IN ('BASE_MOBILE', 'LOW_MOBILE')
  )
GROUP BY c.family_id;
```

이 합계와 `families.internet_product_group`, `internet_contract_months`, `bundle_discount_method`를 사용해 `internet_bundle_discount_rules`의 해당 구간을 선택한다. 인터넷 이용료 자체는 모바일 총액에 더하지 않는다.

### 4.6 사용자별 일 사용량과 월 사용량 만들기

```sql
-- 사용자별·일자별 총 데이터 사용량
SELECT user_id, usage_date, SUM(data_usage_mb) AS daily_data_mb
FROM content_usage
GROUP BY user_id, usage_date;

-- 사용자별 전체 관측기간 사용량
SELECT user_id, SUM(data_usage_mb) / 1024.0 AS observed_data_gb
FROM content_usage
GROUP BY user_id;
```

### 4.7 현재 선택 서비스와 요금제의 선택 가능 후보 비교

```sql
SELECT
    u.user_id,
    p.plan_name,
    available.service_name AS available_service,
    CASE WHEN selected.service_id IS NULL THEN FALSE ELSE TRUE END AS is_selected
FROM users u
JOIN plans p
  ON p.plan_id = u.current_plan_id
JOIN plan_benefits pb
  ON pb.plan_id = p.plan_id
 AND pb.is_selectable = TRUE
JOIN additional_services available
  ON available.service_id = pb.service_id
LEFT JOIN user_services selected
  ON selected.user_id = u.user_id
 AND selected.service_id = pb.service_id;
```

### 4.8 월 사용량·데이터 소진율·월 누적 사용량 계산

아래 예시는 PostgreSQL 기준이다. 먼저 콘텐츠 상세 행을 사용자·날짜 단위로 합친 뒤 월 집계를 만들기 때문에, 상세분류 수에 따른 중복 합산을 피할 수 있다.

```sql
WITH daily_usage AS (
    SELECT
        user_id,
        usage_date,
        SUM(data_usage_mb) AS daily_data_mb
    FROM content_usage
    GROUP BY user_id, usage_date
),
monthly_usage AS (
    SELECT
        user_id,
        DATE_TRUNC('month', usage_date)::date AS usage_month,
        SUM(daily_data_mb) / 1024.0 AS monthly_usage_gb,
        COUNT(*) AS observed_days
    FROM daily_usage
    GROUP BY user_id, DATE_TRUNC('month', usage_date)::date
)
SELECT
    m.user_id,
    m.usage_month,
    m.monthly_usage_gb,
    m.observed_days,
    p.data_limit_gb,
    CASE
        WHEN p.is_unlimited THEN NULL
        WHEN p.data_limit_gb > 0 THEN m.monthly_usage_gb / p.data_limit_gb
        ELSE NULL
    END AS quota_utilization
FROM monthly_usage m
JOIN users u ON u.user_id = m.user_id
JOIN plans p ON p.plan_id = u.current_plan_id;
```

`quota_utilization`은 비율이므로 `1.0`이 기본 제공량 100%에 해당한다. 무제한 요금제는 소진율 개념을 적용하지 않아 Null로 둔다. 현재 90일 관측구간의 첫 달과 마지막 달은 일부 날짜만 포함될 수 있으므로, 완전한 월끼리 비교할 때는 `observed_days`와 해당 월의 달력 일수를 확인한다.

월중 소진 흐름은 다음처럼 계산한다.

```sql
WITH daily_usage AS (
    SELECT
        user_id,
        usage_date,
        SUM(data_usage_mb) AS daily_data_mb
    FROM content_usage
    GROUP BY user_id, usage_date
)
SELECT
    user_id,
    usage_date,
    daily_data_mb,
    SUM(daily_data_mb) OVER (
        PARTITION BY user_id, DATE_TRUNC('month', usage_date)
        ORDER BY usage_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / 1024.0 AS month_to_date_usage_gb
FROM daily_usage;
```

### 4.9 콘텐츠 상세분류를 초이스 서비스에 연결

`content_usage`에는 `service_id`가 없으므로 아래 의미 매핑을 명시적으로 적용한다. `other_*`, `general_*`, `other`는 특정 서비스로 연결하지 않는다.

```sql
WITH usage_with_service AS (
    SELECT
        user_id,
        usage_date,
        content_category,
        content_detail,
        data_usage_mb,
        CASE
            WHEN content_detail = 'netflix' THEN 'S001'
            WHEN content_detail IN ('youtube_video', 'youtube_shorts', 'youtube_music') THEN 'S002'
            WHEN content_detail = 'tving' THEN 'S003'
            WHEN content_detail = 'genie_music' THEN 'S004'
            WHEN content_detail = 'milli_ebook' THEN 'S005'
            WHEN content_detail = 'disney_plus' THEN 'S006'
            WHEN content_detail = 'google_ai' THEN 'S009'
            ELSE NULL
        END AS mapped_service_id
    FROM content_usage
)
SELECT
    uws.user_id,
    uws.mapped_service_id,
    s.service_name,
    SUM(uws.data_usage_mb) AS service_usage_mb
FROM usage_with_service uws
JOIN additional_services s
  ON s.service_id = uws.mapped_service_id
GROUP BY uws.user_id, uws.mapped_service_id, s.service_name;
```

이 매핑은 실제 서비스 가입 또는 시청 이력을 증명하는 FK가 아니다. 제한적으로 상세화한 콘텐츠 사용량을 현재 선택 혜택과 비교하기 위한 분석 규칙이다.

## 5. 할인 계산 시 주의사항

1. `user_discounts`의 행 수를 할인금액으로 해석하면 안 된다. 이 테이블은 혜택 적용 여부만 저장한다.
2. `D001`은 가족 모바일 할인 풀이다. `families.total_discount_allocation_method`에 따라 사용자별 금액을 다시 배분한다.
3. `D002`는 사용자 자신의 `plans.monthly_fee` 구간으로 금액을 찾는다.
4. `D003`은 대상 사용자의 `plans.monthly_fee × discount_rate`로 계산한다.
5. `D004`는 조건 충족 시 `premium_family_discount_rules.discount_amount`를 적용한다.
6. `D005`는 인터넷 회선 혜택이며 가족 전체 계산에서 한 번만 더한다.
7. 선택약정 할인과 최종 예상 청구액은 이 데이터 모델의 계산 범위가 아니다.
8. 내부 검증용 `current_total_discount_amount`는 CSV에 없으며 `D001~D004`만 합산한다.
9. 가족 단위 최적화에서는 `D001~D005` 전체와 총액/정액 두 방식을 비교한다.
10. 가족 정보를 사용하지 않는 개인 추천은 인터넷·가족 결합 재계산을 제외하거나 현재 할인 유지 가정을 명시해야 한다.

## 6. 현재 스키마의 의도적인 범위와 한계

| 항목 | 가능한 것 | 현재 불가능하거나 가정이 필요한 것 |
|---|---|---|
| 모바일 요금제 추천 | 사용자별 사용량, 현재 요금제, 제공 혜택 비교 | 선택약정까지 포함한 실제 청구액 계산 |
| 가족 추천 | `family_id`로 구성원을 모아 모바일 요금제 조합과 `D001~D005` 비교 | 가족 밖의 미등록 회선 반영 |
| 인터넷 | 높은/낮은 할인 그룹을 사용한 결합 할인 계산 | 상세 인터넷 상품명·실제 인터넷 이용료·인터넷 상품 변경 추천 |
| 가족관계 | 같은 가족 구성원과 가족 인원수 확인 | 부모·자녀·배우자 관계의 정확한 복원 |
| 청소년 할인 | 현재 `D004` 수혜 여부 확인 | 후보 요금제 변경 후 법정대리인 재판정은 관계 데이터 없이 가정 필요 |
| 할인금액 | 정책표로 모바일·인터넷 할인 재계산 | 사용자별 최종 청구액은 output에 없음 |
| 이력 | 현재 활성 결합·혜택의 시작일 확인 | 종료된 과거 이력은 현재 합성 데이터에 없음 |

이 데이터의 주된 목적은 실제 청구서 재현이 아니라, 현재 상태와 정책 규칙을 이용해 모바일 요금제 및 가족결합 추천 로직을 검증하는 것이다.
