# n8n 고정 쿼리 계약

AI는 SQL을 작성하거나 수정하지 않습니다. AI가 반환할 수 있는 값은 `query_id`와 카탈로그에
정의된 parameter뿐입니다.

```json
{
  "query_id": "PERS_002",
  "parameters": {
    "user_id": "U00001",
    "year_month": "2026-09"
  }
}
```

## workflow

1. 운영 또는 개인화 질문을 해당 n8n workflow가 받습니다.
2. AI는 해당 영역 CSV 카탈로그에서 `enabled=true`인 query만 선택합니다.
3. n8n은 query ID를 allowlist로 검사하고 parameter 이름·타입·범위를 검증합니다.
4. n8n 내부의 등록 SQL을 positional parameter로 실행합니다.
5. AI가 SQL 문자열을 반환해도 무시합니다.
6. 결과 행 수가 `max_rows`를 넘으면 실패시키거나 사전 정의된 제한을 적용합니다.

운영 workflow는 [`operations-query-catalog.csv`](query-catalogs/operations-query-catalog.csv)와
`n8n_operations` 계정을 사용합니다. 개인화 workflow는
[`personalization-query-catalog.csv`](query-catalogs/personalization-query-catalog.csv)와
`n8n_personalization` 계정을 사용합니다.

두 계정은 해당 AI View 외에 같은 영역 DW의 공개 마스터 8개를 직접 SELECT할 수 있습니다.
대상은 `plans`, `age_benefits`, `plan_age_benefits`, `additional_services`, `plan_benefits`,
`discounts`, `internet_bundle_discount_rules`, `premium_family_discount_rules`이며
[080 마이그레이션](../../db/schema/080_grant_public_master_read.sql)으로 권한을 부여합니다.
고객·가족·사용량 원본은 계속 AI View를 통해 조회합니다. DB 조회 권한과 n8n 실행 allowlist는
별개이므로 새 마스터 조회를 workflow에서 사용하려면 카탈로그와 n8n 등록 SQL에도 추가해야 합니다.
이 권한 변경만으로 기존 쿼리 카탈로그가 확대되지는 않습니다.

AI에 컬럼과 집계 기준을 전달할 때는 [뷰 스키마 안내](view-schemas/README.md)에 따라
해당 영역의 스키마 CSV를 쿼리 카탈로그와 함께 제공합니다. 스키마 CSV는 뷰 해석용이며,
실행할 수 있는 쿼리와 parameter는 기존 쿼리 카탈로그를 기준으로 합니다.

## 운영 002·005 집계 뷰 반영

운영 카탈로그 002·005의 fixed_sql은 고객·월 선집계 뷰를 사용하고 숫자 month_key로 기간을 제한합니다.
query_id·parameter 이름과 위치·출력 컬럼은 유지합니다.
새 뷰·role_operations_reader 조회 권한은 Lambda가 사용하는 초기화·증분/정정 파이프라인의
130 마이그레이션에 포함됩니다. 기존 DB에 스키마만 적용하려면 DB 관리자가
[130 스키마 파일](../../db/schema/130_install_operations_monthly_preagg_view.sql)을
[DB 적용 안내](../../db/README.md#운영-고객월-선집계-뷰-적용)에 따라 트랜잭션에서 적용합니다.
그다음 n8n의 카탈로그 CSV 입력 또는 별도로 등록한 SQL 본문을 변경된 002·005로 갱신합니다.
저장소 CSV 변경만으로 이미 등록된 외부 workflow SQL이 자동으로 갱신되지는 않습니다.

앞 Code 노드는 카탈로그 fixed_sql을 선택하므로 파라미터·allowlist·응답 변환 코드와
프론트 요청 형식의 변경은 필요 없습니다. 현재 DB 적용과 외부 n8n 갱신은 사용자가 수행합니다.
운영 계정 측정 파일은 64MB·force_custom_plan·jit off를 트랜잭션 안에서만 적용하며,
운영 계정의 영구 설정이나 n8n 연결 풀의 세션 설정을 바꾸지 않습니다.
측정 조건을 실제 n8n에서도 계속 사용하려면 해당 연결/트랜잭션에 같은 설정을 따로 적용해야 합니다.

개인화의 사용자 단위 쿼리는 `user_id`와 `name`을 함께 반환합니다. 이름을 가져오기 위한
별도 쿼리를 연쇄 실행하지 않습니다.
