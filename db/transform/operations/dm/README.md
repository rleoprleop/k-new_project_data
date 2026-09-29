# Operations DM

운영 DM은 다음 데이터를 한 번에 조회할 수 있는 Star Schema입니다.

- 현재 가입자 수: 전체, 요금제, 연령대
- 일별·월별 총사용량
- 요금제×연령대×category 사용량
- 가명 고객별 일 사용량과 월 category 사용량
- 가족결합·KT 인터넷 현황
- 현재 선택 서비스와 할인 분포

주요 Dimension은 `dim_date`, `dim_plan`, `dim_age_band`, `dim_content_category`,
`dim_analysis_customer`, `dim_analysis_family`, `dim_service`, `dim_discount`입니다.
집계 테이블은 `daily_usage_segment`, `monthly_usage_segment`, `customer_daily_usage`,
`customer_monthly_category_usage`이며 `fact_` 접두사를 사용하지 않습니다.
