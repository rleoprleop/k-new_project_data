# KT 합성 분석용 데이터 스키마

이 문서는 `generator/data/generated_analysis/`에 생성되는 가명화 분석용 CSV의 실제 컬럼, 관계, grain과 사용 방법을 설명한다. 원본 식별자와 정확한 날짜가 필요한 생성 검증에는 `generator/data/generated/`와 [원본 데이터 스키마](raw-data-schema.md)를 사용한다. 데이터 생성 기준과 합성 가중치는 [생성 상세 사양](generation-spec.md)를 참고한다.

## 1. 분석용 출력을 사용하는 이유

분석용 출력은 원본 성격의 합성 데이터와 같은 사용량·요금제·혜택·할인 상태를 유지하면서, 분석에 불필요한 식별 정보와 날짜 정밀도를 줄인다.

| 목적 | 사용할 출력 |
|---|---|
| 추천 Feature 설계, 사용량 분석, 요금제·혜택 비교 | `generator/data/generated_analysis/` |
| 생성 결과 검증, 원본 ID 추적, 정확한 시작일 확인 | `generator/data/generated/` |

분석용 디렉터리에는 원본과 동일한 이름의 CSV 14개와 `analysis_manifest.json`이 생성된다. 매니페스트에는 기준일, 변환 설명과 테이블별 행 수가 기록된다.

## 2. 원본에서 분석용으로 변환되는 정보

| 원본 정보 | 분석용 정보 | 처리 |
|---|---|---|
| `user_id` | `analysis_user_key` | 사용자 도메인의 HMAC-SHA256 기반 가명 키 |
| `family_id` | `analysis_family_key` | 가족 도메인의 HMAC-SHA256 기반 가명 키 |
| `bundle_composition_id` | `analysis_bundle_composition_key` | 결합 구성요소 도메인의 HMAC-SHA256 기반 가명 키 |
| `name` | 없음 | 제외 |
| `age` | `age_band` | 연령 구간으로 범주화 |
| `subscription_start_date` | `subscription_cohort`, `tenure_months` | 월 코호트와 기준일 현재 가입 개월 수로 변환 |
| `start_date`, `end_date` | `start_month`, `end_month` | `YYYY-MM` 월 단위로 변환 |
| `content_usage.usage_date` | `usage_date` | 일별 추세 분석을 위해 `YYYY-MM-DD` 유지 |
| 행 식별용 ID | 없음 | `content_usage_id`, `user_discount_id`, `user_service_id` 제외 |

가명 키는 같은 가명화 비밀키와 같은 원본 값에 대해 재실행해도 동일하므로 테이블 간 조인이 가능하다. 사용자·가족·결합 구성요소는 서로 다른 도메인으로 계산하므로 원본 문자열이 같아도 같은 가명 키가 되지 않는다. 원본 값이 Null이면 가명 키도 Null이다.

가명화 비밀키를 변경하면 새 출력의 키도 달라지므로 서로 다른 비밀키로 만든 배치끼리는 직접 조인할 수 없다. 기본 비밀키는 이 합성 데이터 프로젝트에만 사용하며 실제 데이터에는 별도 비밀값을 전달해야 한다.

### 연령 구간

| `age_band` | 원본 연령 범위 |
|---|---:|
| `8-12` | 8~12세 |
| `13-18` | 13~18세 |
| `19-24` | 19~24세 |
| `25-34` | 25~34세 |
| `35-49` | 35~49세 |
| `50-64` | 50~64세 |
| `65+` | 65세 이상 |

`tenure_months`는 `analysis_manifest.json`의 `reference_date`를 기준으로 연도와 월 차이를 계산한다. 일(day) 차이는 반영하지 않는다.

## 3. 파일과 정확한 컬럼

### 3.1 변환되는 테이블

#### `users.csv`

한 행은 분석 사용자 한 명이다.

| 컬럼 | Null | 키 | 설명 |
|---|---|---|---|
| `analysis_user_key` | 불가 | PK | 가명 사용자 키 |
| `age_band` | 불가 |  | 연령 구간 |
| `gender` | 불가 |  | `F` 또는 `M` |
| `subscription_cohort` | 불가 |  | 가입 시작 월 `YYYY-MM` |
| `tenure_months` | 불가 |  | 기준일 현재 가입 개월 수 |
| `current_plan_id` | 불가 | FK → `plans.plan_id` | 현재 모바일 요금제 |
| `analysis_family_key` | 허용 | FK → `families.analysis_family_key` | 가명 가족 키. Null이면 독립 사용자 |

#### `families.csv`

한 행은 가족 그룹 하나다. 원본 `family_id`만 `analysis_family_key`로 바뀌고 나머지 컬럼은 동일하다.

```text
analysis_family_key, has_bundle, bundle_type, has_kt_internet,
internet_product_group, internet_contract_months, internet_status,
bundle_discount_method, total_discount_allocation_method,
internet_benefit_discount_id
```

`analysis_family_key`가 PK이며 `internet_benefit_discount_id`는 `discounts.discount_id`를 참조한다.

#### `bundle_discount_compositions.csv`

한 행은 결합에 참여한 인터넷 또는 모바일 구성요소 하나다.

| 컬럼 | Null | 키 | 설명 |
|---|---|---|---|
| `analysis_bundle_composition_key` | 불가 | PK | 가명 결합 구성요소 키 |
| `analysis_family_key` | 불가 | FK → `families` | 구성요소가 속한 가족 |
| `component_type` | 불가 |  | `INTERNET` 또는 `MOBILE` |
| `analysis_user_key` | 조건부 허용 | FK → `users` | 모바일 구성요소 사용자. 인터넷은 Null |
| `component_role` | 불가 |  | 결합 계산 역할 |
| `status` | 불가 |  | 현재 생성값은 `ACTIVE` |
| `start_month` | 불가 |  | 참여 시작 월 `YYYY-MM` |
| `end_month` | 허용 |  | 종료 월. 현재 활성 행은 Null |

#### `user_discounts.csv`

한 행은 사용자에게 적용된 할인 혜택 하나다. 원본의 행 식별자 `user_discount_id`는 제외된다.

| 컬럼 | Null | 키 | 설명 |
|---|---|---|---|
| `analysis_user_key` | 불가 | FK → `users` | 할인 수혜 사용자 |
| `analysis_bundle_composition_key` | 불가 | FK → `bundle_discount_compositions` | 대상 모바일 구성요소 |
| `discount_id` | 불가 | FK → `discounts` | 적용 혜택 `D001`~`D004` |
| `status` | 불가 |  | 현재 생성값은 `ACTIVE` |
| `start_month` | 불가 |  | 적용 시작 월 |
| `end_month` | 허용 |  | 종료 월. 활성 혜택은 Null |

논리 grain은 `(analysis_user_key, analysis_bundle_composition_key, discount_id, start_month)`이다. 할인금액이 아니라 혜택 적용 여부를 나타낸다.

#### `user_services.csv`

한 행은 사용자가 실제 선택한 초이스 서비스 하나다. 원본의 행 식별자 `user_service_id`는 제외된다.

| 컬럼 | Null | 키 | 설명 |
|---|---|---|---|
| `analysis_user_key` | 불가 | FK → `users` | 서비스 선택 사용자 |
| `service_id` | 불가 | FK → `additional_services` | 실제 선택 서비스 |
| `benefit_type` | 불가 |  | `CHOICE`, `PLUS`, `DOUBLE_CHOICE` |
| `start_month` | 불가 |  | 선택 적용 시작 월 |

논리 grain은 `(analysis_user_key, service_id, benefit_type, start_month)`이다. 초이스 더블 사용자는 복수 행을 가질 수 있다.

#### `content_usage.csv`

한 행은 사용자·날짜·콘텐츠 대분류·상세분류별 데이터 사용량이다. 원본의 행 식별자 `content_usage_id`는 제외된다.

| 컬럼 | Null | 키 | 설명 |
|---|---|---|---|
| `analysis_user_key` | 불가 | FK → `users` | 사용 사용자 |
| `usage_date` | 불가 | 복합 grain | 사용 일자 `YYYY-MM-DD` |
| `content_category` | 불가 | 복합 grain | 콘텐츠 대분류 |
| `content_detail` | 불가 | 복합 grain | 제한적 상세분류 |
| `data_usage_mb` | 불가 |  | 해당 날짜·분류의 데이터 사용량 MB |

논리 grain은 `(analysis_user_key, usage_date, content_category, content_detail)`이다. 사용자별 활성 상세분류 수가 달라 사용자·날짜별 행 수는 일정하지 않다.

### 3.2 원본과 동일하게 유지되는 마스터·정책 테이블

다음 8개 CSV는 원본과 컬럼 및 값이 동일하다.

| 파일 | 역할 |
|---|---|
| `plans.csv` | 모바일 요금제 마스터 |
| `age_benefits.csv` | 연령 혜택 마스터 |
| `plan_age_benefits.csv` | 요금제별 연령 혜택 값 |
| `additional_services.csv` | 부가서비스 마스터 |
| `plan_benefits.csv` | 요금제와 부가서비스 제공 관계 |
| `discounts.csv` | 할인 식별자 마스터 |
| `internet_bundle_discount_rules.csv` | 총액·정액·인터넷 할인 정책 구간 |
| `premium_family_discount_rules.csv` | 프리미엄 가족결합 정책 |

각 컬럼과 enum의 상세 의미는 [원본 데이터 스키마의 상세 데이터 사전](raw-data-schema.md#3-상세-데이터-사전)을 그대로 적용한다.

## 4. 관계와 카디널리티

`1:0..N`의 N쪽을 그대로 조인하면 부모 행이 여러 번 나타난다. 사용자 수, 요금제 수, 월정액을 계산할 때는 필요한 grain으로 먼저 집계한다.

| 부모 테이블 | 자식 테이블 | 관계 | 조인 키 | 주의점 |
|---|---|---|---|---|
| `plans` | `users` | 1:0..N | `plan_id = current_plan_id` | 요금제별 사용자가 여러 명이다. |
| `families` | `users` | 1:0..N | `analysis_family_key` | 독립 사용자는 가족 키가 Null이다. |
| `families` | `bundle_discount_compositions` | 1:0..N | `analysis_family_key` | 인터넷 1행과 모바일 여러 행이 연결된다. |
| `users` | `bundle_discount_compositions` | 1:0..1 | `analysis_user_key` | 인터넷 구성요소에는 사용자 키가 없다. |
| `users` | `user_discounts` | 1:0..N | `analysis_user_key` | 한 사용자가 여러 할인 혜택을 받을 수 있다. |
| `bundle_discount_compositions` | `user_discounts` | 1:0..N | `analysis_bundle_composition_key` | 구성요소에 여러 혜택이 연결될 수 있다. |
| `users` | `user_services` | 1:0..N | `analysis_user_key` | 선택 서비스 수만큼 사용자 행이 증가한다. |
| `additional_services` | `user_services` | 1:0..N | `service_id` | 서비스별 선택자가 여러 명이다. |
| `users` | `content_usage` | 1:0..N | `analysis_user_key` | 날짜·상세분류 수만큼 사용자 행이 증가한다. |
| `plans` | `plan_benefits` | 1:0..N | `plan_id` | 후보·고정 혜택 수만큼 요금제가 반복된다. |

논리적 연결은 다음과 같다.

```text
users ── current_plan_id ──> plans ──> plan_benefits ──> additional_services
  │                              │
  │                              └──> plan_age_benefits ──> age_benefits
  │
  ├── analysis_family_key ──> families ──> bundle_discount_compositions
  ├── analysis_user_key ────> user_discounts ──> discounts
  ├── analysis_user_key ────> user_services ──> additional_services
  └── analysis_user_key ────> content_usage
```

## 5. 분석 예시

아래 예시는 PostgreSQL 기준이다.

### 5.1 사용자와 현재 요금제

```sql
SELECT
    u.analysis_user_key,
    u.age_band,
    u.tenure_months,
    p.plan_name,
    p.monthly_fee,
    p.data_limit_gb,
    p.is_unlimited
FROM users u
JOIN plans p
  ON p.plan_id = u.current_plan_id;
```

### 5.2 월 사용량과 기본 데이터 소진율

콘텐츠 행을 사용자·날짜 단위로 먼저 합산한 뒤 월 단위로 집계한다.

```sql
WITH daily_usage AS (
    SELECT
        analysis_user_key,
        usage_date,
        SUM(data_usage_mb) AS daily_data_mb
    FROM content_usage
    GROUP BY analysis_user_key, usage_date
),
monthly_usage AS (
    SELECT
        analysis_user_key,
        DATE_TRUNC('month', usage_date)::date AS usage_month,
        SUM(daily_data_mb) / 1024.0 AS monthly_usage_gb,
        COUNT(*) AS observed_days
    FROM daily_usage
    GROUP BY analysis_user_key, DATE_TRUNC('month', usage_date)::date
)
SELECT
    m.analysis_user_key,
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
JOIN users u USING (analysis_user_key)
JOIN plans p ON p.plan_id = u.current_plan_id;
```

`quota_utilization=1.0`은 기본 제공량 100%를 뜻한다. 무제한 요금제에는 소진율을 적용하지 않는다. 관측기간의 첫 달과 마지막 달은 일부 날짜만 포함될 수 있으므로 `observed_days`를 함께 확인한다.

### 5.3 월중 누적 사용량

```sql
WITH daily_usage AS (
    SELECT
        analysis_user_key,
        usage_date,
        SUM(data_usage_mb) AS daily_data_mb
    FROM content_usage
    GROUP BY analysis_user_key, usage_date
)
SELECT
    analysis_user_key,
    usage_date,
    daily_data_mb,
    SUM(daily_data_mb) OVER (
        PARTITION BY analysis_user_key, DATE_TRUNC('month', usage_date)
        ORDER BY usage_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) / 1024.0 AS month_to_date_usage_gb
FROM daily_usage;
```

### 5.4 콘텐츠 상세분류와 초이스 서비스 연결

`content_detail`은 `service_id`의 물리 FK가 아니다. 아래 의미 매핑을 분석 규칙으로 적용한다.

| `content_detail` | `service_id` |
|---|---|
| `netflix` | `S001` |
| `youtube_video`, `youtube_shorts`, `youtube_music` | `S002` |
| `tving` | `S003` |
| `genie_music` | `S004` |
| `milli_ebook` | `S005` |
| `disney_plus` | `S006` |
| `google_ai` | `S009` |
| `other_*`, `general_*`, `other` | 연결하지 않음 |

```sql
SELECT
    analysis_user_key,
    CASE
        WHEN content_detail = 'netflix' THEN 'S001'
        WHEN content_detail IN ('youtube_video', 'youtube_shorts', 'youtube_music') THEN 'S002'
        WHEN content_detail = 'tving' THEN 'S003'
        WHEN content_detail = 'genie_music' THEN 'S004'
        WHEN content_detail = 'milli_ebook' THEN 'S005'
        WHEN content_detail = 'disney_plus' THEN 'S006'
        WHEN content_detail = 'google_ai' THEN 'S009'
        ELSE NULL
    END AS mapped_service_id,
    SUM(data_usage_mb) AS service_usage_mb
FROM content_usage
GROUP BY
    analysis_user_key,
    CASE
        WHEN content_detail = 'netflix' THEN 'S001'
        WHEN content_detail IN ('youtube_video', 'youtube_shorts', 'youtube_music') THEN 'S002'
        WHEN content_detail = 'tving' THEN 'S003'
        WHEN content_detail = 'genie_music' THEN 'S004'
        WHEN content_detail = 'milli_ebook' THEN 'S005'
        WHEN content_detail = 'disney_plus' THEN 'S006'
        WHEN content_detail = 'google_ai' THEN 'S009'
        ELSE NULL
    END;
```

Null로 매핑된 일반·기타 콘텐츠를 특정 서비스 사용으로 해석하면 안 된다. 매핑된 값도 실제 구독 이력이 아니라 콘텐츠 사용 성향과 선택 혜택을 비교하기 위한 분석 코드다.

### 5.5 현재 선택 서비스와 사용 성향 비교

먼저 사용량을 사용자·서비스 단위로 집계한 다음 `user_services`와 조인한다. 원시 `content_usage`와 바로 조인하면 선택 서비스 행과 날짜별 사용량 행이 곱해질 수 있다.

```sql
WITH service_usage AS (
    SELECT
        analysis_user_key,
        content_detail,
        SUM(data_usage_mb) AS usage_mb
    FROM content_usage
    WHERE content_detail IN (
        'netflix', 'youtube_video', 'youtube_shorts', 'youtube_music',
        'tving', 'genie_music', 'milli_ebook', 'disney_plus', 'google_ai'
    )
    GROUP BY analysis_user_key, content_detail
)
SELECT
    us.analysis_user_key,
    us.service_id,
    s.service_name,
    su.content_detail,
    su.usage_mb
FROM user_services us
JOIN additional_services s USING (service_id)
LEFT JOIN service_usage su
  ON su.analysis_user_key = us.analysis_user_key
 AND (
      (us.service_id = 'S001' AND su.content_detail = 'netflix')
   OR (us.service_id = 'S002' AND su.content_detail IN ('youtube_video', 'youtube_shorts', 'youtube_music'))
   OR (us.service_id = 'S003' AND su.content_detail = 'tving')
   OR (us.service_id = 'S004' AND su.content_detail = 'genie_music')
   OR (us.service_id = 'S005' AND su.content_detail = 'milli_ebook')
   OR (us.service_id = 'S006' AND su.content_detail = 'disney_plus')
   OR (us.service_id = 'S009' AND su.content_detail = 'google_ai')
 );
```

## 6. 해석 시 주의사항

1. 분석 키는 식별자가 아니라 같은 배치 안에서 조인하기 위한 가명 키다.
2. `start_month`, `end_month`에는 정확한 일자가 없으므로 일 단위 재현에 사용하지 않는다.
3. `content_usage.usage_date`만 일 단위로 유지한다.
4. `content_usage`는 사용자별 활성 상세분류 수가 다르므로 행 수를 사용량이나 활동량으로 해석하지 않는다.
5. 사용량은 반드시 `data_usage_mb`를 합산한다.
6. 무제한 요금제의 `data_limit_gb=Null`은 누락이 아니라 상한 없음이라는 뜻이다.
7. `user_discounts`는 할인 적용 여부이며 금액은 정책 테이블로 계산한다.
8. `user_services`는 실제 선택 서비스이고 `plan_benefits`는 선택 가능한 후보다.
9. 가족·서비스·사용량 테이블을 한 번에 조인하기 전에 각각 필요한 grain으로 집계해야 중복 합산을 피할 수 있다.
10. 할인 계산 규칙과 현재 데이터의 분석 범위는 [원본 데이터 스키마의 할인 계산 주의사항](raw-data-schema.md#5-할인-계산-시-주의사항)을 동일하게 적용한다.
