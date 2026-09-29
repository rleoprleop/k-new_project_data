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

운영 workflow는 [`operations-query-catalog.csv`](../query-catalogs/operations-query-catalog.csv)와
`n8n_operations` 계정을 사용합니다. 개인화 workflow는
[`personalization-query-catalog.csv`](../query-catalogs/personalization-query-catalog.csv)와
`n8n_personalization` 계정을 사용합니다.

개인화의 사용자 단위 쿼리는 `user_id`와 `name`을 함께 반환합니다. 이름을 가져오기 위한
별도 쿼리를 연쇄 실행하지 않습니다.
