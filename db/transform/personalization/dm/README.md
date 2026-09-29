# Personalization DM

개인화 DM은 고객·일자·요금제·콘텐츠·서비스·할인·가족 Dimension을 연결합니다.
`dim_customer`에는 `user_id`와 `name`을 함께 저장하며 개인화 AI View도 두 값을 함께
반환합니다.

| 객체 | 확인 가능한 데이터 |
| --- | --- |
| `customer_daily_usage` | 하루 총사용량과 월 누적 사용량 |
| `customer_content_daily_usage` | 선택 일자의 category/detail 드릴다운 View |
| `customer_monthly_usage` | 월 총사용량과 일평균 |
| `customer_monthly_content_usage` | 월 category/detail 사용량 |
| `customer_service_current` | 현재 선택 서비스 |
| `customer_discount_current` | 현재 할인 |
| `customer_family_current` | 가족결합과 인터넷 상태 |
| `bridge_service_content` | 선택 서비스와 관련 detail 매핑 |

최근 7일·30일과 추천 판단용 입력은 Feature Snapshot으로 저장하지 않고 고정 쿼리가
일별 집계에서 계산합니다. 데이터베이스는 추천 결과를 만들지 않습니다.
