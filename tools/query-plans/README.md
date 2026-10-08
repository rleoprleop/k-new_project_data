# 운영 쿼리 비교와 실행계획 확인

`OPS_ANALYSIS_002`(월별 평균·중앙값)와 `OPS_ANALYSIS_005`(분포·집중도)의
원래 SQL과 최종 최적화 SQL을 같은 DB에서 비교합니다.
최적화 뷰는 [130 스키마 파일](../../db/schema/130_install_operations_monthly_preagg_view.sql)과
파이프라인에서 관리합니다. 여기의 도구는 영구 뷰·인덱스·권한을 변경하지 않습니다.

| 파일 | 용도 |
| --- | --- |
| `compare_operations_reader_preagg.psql` | 네 기간의 실행시간을 워밍업 후 교대로 반복 측정하고 중앙값·최솟값·최댓값 출력 |
| `explain_operations_preagg.psql` | 지정한 기간의 원래·최종 SQL 네 개에 대한 상세 실행계획 출력 |
| `ops_analysis_002.sql`, `ops_analysis_005.sql` | 최적화 전 SQL. 전후 비교의 고정 기준 |
| `ops_analysis_002_optimized.sql`, `ops_analysis_005_optimized.sql` | 운영 카탈로그와 같은 최종 SQL |
| `measurement_settings.sql` | 측정 트랜잭션의 공통 `work_mem=64MB` 설정 |

## 실행 전 준비

PostgreSQL 15 이상과 psql을 사용합니다. 뷰가 설치된 DB에 `n8n_operations`로 직접 접속하고,
열린 트랜잭션이 없는 프롬프트에서 실행합니다. 관리자 세션의 `SET ROLE`은 허용하지 않습니다.
두 AI 뷰의 SELECT 권한과, 시간 비교 도구에서 임시 표를 만들 DB의 TEMP 권한이 필요합니다.
기존 DB에 뷰만 적용하는 방법은 [DB 안내](../../db/README.md#운영-고객월-선집계-뷰-적용)에 있습니다.

두 도구는 같은 repeatable read 읽기 전용 스냅샷에서 SELECT를 실행하며,
측정 트랜잭션에만 `work_mem=64MB`, `force_custom_plan`, `jit=off`, 잠금 대기 5초를 적용합니다.
시간 비교 도구는 임시 결과 표의 생성·제거에만 별도 쓰기 트랜잭션을 사용합니다.
정상 종료하면 설정을 복구합니다. 오류·취소 후에는 `rollback;`을 실행합니다.
문장 제한 시간은 접속 계정의 설정을 유지하며 선택적으로 `reader_plan_timeout`을 지정할 수 있습니다.
이 설정은 n8n 연결 풀이나 계정의 영구 설정을 변경하지 않습니다.

## 실행시간 비교

```psql
\set plan_month 2026-08-01
\set reader_plan_repeats 5
\i C:/kt_nd/tools/query-plans/compare_operations_reader_preagg.psql
```

`plan_month`는 마지막 포함 월의 첫날입니다. 기본 2026년 8월이면 1개월은 8월,
6개월은 3~8월, 12개월은 2025년 9월~2026년 8월입니다.
전체 기간은 기존 카테고리 뷰의 최소 월부터 최대 월 다음 달까지로 자동 계산합니다.
기간은 시작 포함·종료 제외이며, 기록 없는 월도 달력 범위에 포함될 수 있습니다.
`reader_plan_repeats`는 1~10 사이이며 기본 5입니다.
각 쿼리·기간·방식을 한 번 워밍업하고 교대로 측정합니다.
`time_reduction_pct`가 양수면 최적화 SQL의 중앙값이 더 짧습니다.
요약의 `filtered_*` 컬럼은 최종 최적화 SQL의 결과입니다.

이 도구는 `EXPLAIN ANALYZE`로 실제 SELECT를 실행하지만 상세 계획이나 고객 결과는 출력하지 않습니다.
행 수를 내부 측정 지표로 저장하고 시간 요약을 출력합니다. 모든 결과 값의 동등성을 검사하는 도구는 아닙니다.

## 상세 실행계획 확인

```psql
\set plan_start_date 2026-03-01
\set plan_end_date_exclusive 2026-09-01
\set plan_analyze true
\i C:/kt_nd/tools/query-plans/explain_operations_preagg.psql
```

두 날짜는 월의 첫날이어야 하고 시작일이 종료 경계보다 앞서야 합니다.
원래·최종 002, 원래·최종 005의 네 계획을 query_id·variant와 함께 출력합니다.
기본 `plan_analyze=true`는 네 SELECT를 각각 한 번 실행하고 실제 행 수·버퍼·전체 실행시간을 표시합니다.
워밍업과 반복 중앙값 측정은 하지 않으므로 성과 수치는 시간 비교 도구에서 확인합니다.
`plan_analyze=false`는 SELECT를 실행하지 않고 예상 계획만 출력합니다.

SQL은 영구 뷰를 조회합니다. 월 필터가 fact 스캔까지 내려가는지,
고객·날짜 차원 조인 전에 숫자 고객·월 키로 집계하는지 확인합니다.

## 출력 저장과 입력 초기화

```psql
\o C:/kt_nd/.local/operations-preagg-plans.txt
\i C:/kt_nd/tools/query-plans/explain_operations_preagg.psql
\o
```

저장 폴더는 먼저 준비합니다. 오류는 콘솔에서 확인합니다.
psql 입력 변수는 실행 후에도 남으므로 다음 실행 전에 값을 지정하거나 `\unset`으로 제거합니다.
두 도구의 `ON_ERROR_STOP`과 pager 설정도 세션에 남습니다.

최적화 이유와 기존 측정 결과는 [이슈 기록](../../docs/issues/operations-query-optimization.md)에 있습니다.
