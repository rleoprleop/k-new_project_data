# 개인화 DM

`dm_personalization`은 사용자별 Star Schema와 추천용 Feature Snapshot을 만든다. `fact_customer_daily_usage`는 `dim_customer`, `dim_date`, `dim_plan`, `dim_content`와 함께 조회한다.

Fact grain은 **사용자 × 사용 일자 × 콘텐츠 대분류/상세분류**다.
`source_batch_id`는 마지막 계산 실행의 계보이며 `customer_key`는
`dim_customer.user_id`와 연결된다.

| 측정값 | 의미 |
| --- | --- |
| `data_usage_mb` | 해당 콘텐츠의 당일 사용량 |
| `daily_total_usage_mb` | 사용자·날짜의 전체 콘텐츠 사용량 |
| `month_to_date_usage_mb` | 달력 월 시작부터 해당 사용일까지의 누적 사용량 |
| `quota_utilization` | 월 누적 MB ÷ 기본 제공 MB; 무제한·0·Null 제공량이면 Null |

`daily_total_usage_mb`와 `month_to_date_usage_mb`는 콘텐츠 행마다 반복되므로 전체 Fact에서 단순 합산하지 않는다.

`customer_usage_feature_snapshot`의 grain은 **`user_id` × `feature_reference_date`**다.
성공적으로 처리한 관측 날짜마다 사용자별 Snapshot을 만든다.

| Feature | 계산 범위 |
| --- | --- |
| `trailing_7d_usage_mb` | 기준일 포함 최근 7일 합계 |
| `trailing_30d_usage_mb` | 기준일 포함 최근 30일 합계 |
| `content_category_usage_ratio` | 최근 30일 대분류별 사용량 비율(JSONB) |
| `preferred_content_category` | 최근 30일 사용량이 가장 큰 대분류 |
| `month_to_date_usage_mb` | 기준일이 속한 달의 누적 사용량 |
| `plan_quota_utilization` | 월 누적 사용량 ÷ 현재 요금제 기본 제공량 |

현재 요금제는 `customer_profile.current_plan_id`를 기준으로 한다. 원천에 변경 이력이 없어 과거 요금제는 복원하지 않는다. 사용량이 없는 관측 구간에는 콘텐츠 비율이 빈 객체이고 선호 콘텐츠가 Null일 수 있다.

SQL은 [스키마](../../../schema/050_dm_personalization.sql), [Fact·Feature 생성](010_build.sql), [합계 검증](../../../quality/personalization/dm/010_quality.sql)으로 나뉜다. 전체 실행 방법은 [SQL 실행](../../../../pipeline/SQL_EXECUTION.md)을 참고한다.
