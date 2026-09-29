# 개인화 DW

`dw_personalization`은 추천 결과를 사용자에게 연결하기 위해 `user_id`와 일별 사용자 grain을 유지한다. 정확한 서비스 시작·종료일도 유지하므로 접근을 제한해야 한다. 비개인정보 마스터는 `dw_common`에서 공유한다.

| 테이블 | 내용 | grain |
| --- | --- | --- |
| `customer_profile` | 사용자 ID, 나이·성별·가입 시작일·현재 요금제·가족 ID | 사용자 |
| `customer_identity_bridge` | 사용자 ID와 이름 | 사용자 |
| `family` | 가족 ID와 명시 컬럼으로 저장한 결합·인터넷 속성 | 가족 |
| `bundle_composition` | 결합 구성요소와 정확한 시작·종료일 | 결합 구성요소 |
| `user_discount` | 할인 적용과 정확한 시작·종료일 | 사용자 × 구성요소 × 할인 × 시작일 |
| `user_service` | 선택 서비스와 정확한 시작일 | 사용자 × 서비스 × 혜택 유형 × 시작일 |
| `content_usage` | 일자·콘텐츠 대/상세분류별 사용량 | 사용자 × 일자 × 대·상세분류 |

추천 계산에 필요 없는 `name`은 일반 테이블에 반복 저장하지 않고 `customer_identity_bridge`에만 둔다. 현재 DDL은 개인화 스키마와 bridge의 PUBLIC 권한을 회수한다. 실제 실행·조회 역할의 GRANT와 권한 검증은 배포 시 별도로 필요하다.

`source_batch_id`는 업무 키가 아니라 마지막 적재 실행의 계보다. `family_id`를 업무
키로 사용하며 Raw의 나머지 속성을 각각 같은 자료형의 명시 컬럼으로 적재한다.
`attributes` JSONB는 사용하지 않는다.

SQL은 [스키마](../../../schema/030_dw_personalization.sql), [변환](010_build.sql), [검증](../../../quality/personalization/dw/010_quality.sql)으로 나뉜다. 검증은 가족 9개 속성과 가족 ID·배치 ID의 Raw 대조 및 사용량 합계를 확인한다. 전체 실행 방법은 [SQL 실행](../../../../pipeline/SQL_EXECUTION.md)을 참고한다.
