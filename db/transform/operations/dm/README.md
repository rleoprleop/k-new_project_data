# 운영 DM

`dm_operations`는 운영 DW를 기반으로 일별 사용 현황을 조회하는 Star Schema다.

| 테이블 | 역할 |
| --- | --- |
| `dim_date` | 일자·월·분기·요일·주말 구분 |
| `dim_plan` | 현재 요금제 이름·종류·가격·제공량 |
| `dim_content` | 콘텐츠 대분류와 상세분류 |
| `dim_age_band` | 연령 구간과 범위 |
| `fact_daily_usage_summary` | 사용량·활성 사용자 수·평균 사용량·사용 건수 |

Fact grain은 **배치 × 사용 일자 × 현재 요금제 × 연령 구간 × 콘텐츠 대분류/상세분류**다. 측정값은 해당 grain의 `total_usage_mb` 합계, `active_user_count` 고유 가명 사용자 수, `average_usage_mb` 사용자당 평균, `usage_event_count` 원천 행 수다. 날짜는 현재 `date_key` FK가 아니라 `usage_date` 값으로 Dimension과 연결한다.

동일 사용자가 여러 콘텐츠 분류에 나타날 수 있으므로 Fact 행의 `active_user_count`를 단순 합산해 전체 고유 사용자 수로 해석하면 안 된다.

SQL은 [스키마](../../../schema/040_dm_operations.sql), [생성](010_build.sql), [합계 검증](../../../quality/operations/dm/010_quality.sql)으로 나뉜다. 전체 실행 방법은 [SQL 실행](../../../../pipeline/SQL_EXECUTION.md)을 참고한다.
