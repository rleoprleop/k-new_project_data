# Landing 적재·공통 마스터 영역

`db/load`는 운영·개인화 파이프라인이 공유하는 원본 적재 단계입니다. `generator/data/generated/*.csv`의 원본 14개 파일을 받아 Landing Raw와 감사 이력을 만들고, 이후 공통 마스터 생성 단계로 연결합니다.

| 논리 스키마 | 역할 |
| --- | --- |
| `landing` | 원본 ID와 값을 유지하는 배치별 `raw_*` 테이블. 운영·개인화 DW의 유일한 입력이다. |
| `audit` | 배치 ID·상태·오류, 파일별 SHA-256·행 수, 품질 검사 결과를 기록한다. |
| `dw_common` | 요금제·할인·부가서비스·혜택·정책 등 두 영역이 함께 쓰는 비개인정보 마스터다. |

## 처리 순서

1. [`../schema/001_audit_landing_common.sql`](../schema/001_audit_landing_common.sql)이 `landing`, `audit`, `dw_common`의 테이블과 제약조건을 만든다.
2. [`010_load_landing_raw.psql`](010_load_landing_raw.psql)이 같은 배치의 Raw 행을 교체하고 PostgreSQL `\copy`로 CSV를 적재한 뒤, 파일별 체크섬과 적재 행 수를 기록한다.
3. [`../quality/010_landing_raw.sql`](../quality/010_landing_raw.sql)이 사용자·가족·요금제·정책 등의 참조 관계, 사용량 grain 중복, 음수 사용량을 검사한다. 실패하면 DW/DM 생성으로 진행하지 않는다.
4. [`../transform/common/010_load_master.sql`](../transform/common/010_load_master.sql)이 `plan`, `discount`, `additional_service` 및 혜택·정책 테이블을 `dw_common`에 UPSERT한다.

증분 경로는 [`005_load_landing_master.psql`](005_load_landing_master.psql)로 13개
스냅샷 파일을 초기화하고, [`020_load_incremental_content_usage.psql`](020_load_incremental_content_usage.psql)로
하나 이상의 일별 `content_usage` 파티션과 파일 manifest를 같은 트랜잭션에 적재합니다.

이후 같은 Raw 배치에서 [운영 DW](../transform/operations/dw/README.md)와 [개인화 DW](../transform/personalization/dw/README.md)가 갈라진다. 전체 트랜잭션 순서와 재실행 방식은 [SQL 실행](../../pipeline/SQL_EXECUTION.md)을 참고한다.
