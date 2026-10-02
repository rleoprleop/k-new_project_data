# Database

PostgreSQL 15 이상에서 운영 분석과 개인화 분석을 시스템적으로 분리하는 DW/DM입니다.

```text
S3 또는 로컬 CSV (스냅샷 13개 + 콘텐츠 사용량 CSV/날짜 파티션)
  → pg_temp staging (배치 트랜잭션 동안만 존재)
  ├─ dw_operations       HMAC 가명 키, category 사용량
  │   └─ dm_operations  운영 집계 Star Schema
  │       → ai_operations View
  └─ dw_personalization  user_id·name·content_detail 유지
      └─ dm_personalization  개인화 Star Schema
          → ai_personalization View
```

영구 Landing과 `dw_common`은 사용하지 않습니다. 14개 원천 논리 테이블은 두 DW에
각각 존재하며, 운영 DW만 사용자·가족·연결 키를 즉시 HMAC으로 치환합니다.

| 스키마 | 역할 |
| --- | --- |
| `audit` | 배치 상태, 파일 checksum·행 수, 워터마크, 품질 결과 |
| `dw_operations` | 이름·원본 ID·detail이 없는 운영 상세 데이터 |
| `dw_personalization` | `user_id`, `name`, 제한적 `content_detail`을 포함한 개인화 상세 데이터 |
| `dm_operations` | 가입자·가족·서비스·할인과 일/월 운영 집계 |
| `dm_personalization` | 고객 일/월 사용량, 월 detail 집계, 현재 상태 Dimension |
| `ai_operations` | 운영 n8n 고정 쿼리 전용 View |
| `ai_personalization` | 개인화 n8n 고정 쿼리 전용 View. 사용자 결과에 `name` 포함 |

`content_usage`의 개인화 원자 grain은 사용자×일자×category×detail입니다. 약 5천만 건의
상세 행을 다시 복제하지 않도록 `dm_personalization.customer_content_daily_usage`는 DW를
스타 형태로 연결한 View이고, 일 합계와 월 합계·월 detail은 물리 테이블입니다.

실행 순서는 `schema → pg_temp staging → staging quality → DW → DM → DW/DM quality`입니다.
[`pipeline/`](../pipeline/README.md)이 두 영역을 같은 배치 트랜잭션에서 처리하며,
`content_usage_daily` 워터마크를 공유합니다. AWS에서는
[`Lambda Handler`](../deploy/lambda/README.md)가 S3 파일을 내려받아 같은 파이프라인을
호출합니다. 저장소에는 연결 문자열·비밀번호·키를 기록하지 않습니다.
