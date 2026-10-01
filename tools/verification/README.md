# 적재 후 검증 사용 방법

[verify_loaded_data.psql](verify_loaded_data.psql)은 `content_usage_daily` 파이프라인의
실행 이력, 워터마크, 기록된 품질 결과와 선택적인 DW/DM 사용량 총합을 조회한다.
로컬 파일의 SQL을 연결된 PostgreSQL에서 실행하며 데이터·스키마·audit 기록을 변경하지 않는다.

## 실행 전 준비

1. Lambda 적재 호출이 종료됐는지 CloudWatch 로그의 동일 RequestId에 대한 `REPORT`로 확인한다.
   호출 종료와 적재 성공은 다르므로 성공 여부는 검증 결과도 확인한다.
2. 기존에 사용하던 접속 명령으로 로컬 `psql`에서 대상 RDS 데이터베이스에 접속한다.
   연결 문자열·비밀번호·키는 이 문서나 검증 파일에 저장하지 않는다.
3. 기존 트랜잭션이 없는 세션에서 실행한다. 다른 작업의 트랜잭션이 열려 있다면
   먼저 해당 작업을 처리하거나 새 `psql` 세션으로 접속한다.

아래 `\i`, `\set` 명령은 PowerShell이 아니라 **접속된 psql 프롬프트**에서 실행한다.
검증 파일의 절대 경로를 사용하므로 PowerShell의 현재 폴더는 상관없다.

## 기본 검증 실행

```psql
\set verify_totals false
\i C:/kt_nd/tools/verification/verify_loaded_data.psql
```

기본 실행은 다음 세 항목을 조회한다. 전체 사용량 테이블은 스캔하지 않는다.

### 1. 최근 실행 이력

최근 10개 배치의 상태와 처리 날짜를 표시한다.

- 완료하려던 최신 배치가 `SUCCEEDED`인지 확인한다.
- 오류 해결 과정에서 남은 과거 `FAILED` 이력 자체는 현재 데이터의 실패를 뜻하지 않는다.
- `RUNNING` 이력은 실제 Lambda가 아직 실행 중이라는 증거가 아니다.
  타임아웃 등으로 상태가 남을 수 있으므로 CloudWatch 로그로 확인한다.

### 2. 워터마크

| 항목 | 해석 |
| --- | --- |
| `watermark_check = PASS` | 워터마크가 성공한 증분 배치의 종료 날짜와 일치 |
| `watermark_check = FAIL` | 워터마크와 연결된 배치 상태·날짜 등이 일치하지 않음 |
| `watermark_check = NO_WATERMARK` | 초기화만 완료됐거나 성공한 증분 적재가 아직 없음 |
| `last_successful_event_date` | 적재가 완료된 마지막 날짜. 의도한 종료 날짜인지 직접 확인 |
| `yesterday_kst` | 검증 시점의 한국 시간 기준 어제 날짜 |
| `caught_up_through_yesterday = t` | 워터마크가 한국 시간 기준 어제까지 도달 |

`caught_up_through_yesterday = f`라도 과거 날짜까지만 적재하려던 경우에는 정상일 수 있다.
워터마크가 없으면 이 값은 NULL이다. `PASS`만 보고 목표 날짜까지 완료됐다고 판단하지 않는다.

### 3. 기록된 품질 결과

성공한 모든 배치에서 아래 조건을 확인한다.

- `checked_rules > 0`
- `failed_rows = 0`
- `recorded_quality_check = PASS`

`MISSING_QUALITY_RESULTS`는 성공 배치에 품질 결과가 없다는 뜻이다.
조회 결과가 0행이면 성공 배치가 없는 것이므로 검증 통과로 해석하지 않는다.

이 항목은 저장된 결과를 조회할 뿐 기존 품질 SQL을 재실행하지 않는다.
모든 개별 규칙이 빠짐없이 실행됐는지까지 증명하지는 않는다.
실패 배치의 품질 기록은 롤백될 수 있어, 실패 결과가 없다는 사실만으로 성공을 판단하면 안 된다.

## 선택: 전체 DW/DM 사용량 총합 비교

기본 결과를 먼저 확인한 뒤 필요할 때 실행한다.

```psql
\set verify_totals true
\i C:/kt_nd/tools/verification/verify_loaded_data.psql
\set verify_totals false
```

`verify_totals` 값은 현재 psql 세션에 남으므로 마지막 명령으로 기본 모드로 되돌린다.
이 모드는 기본 세 항목과 함께 아래 네 테이블의 전체 행 수·사용량 합계를 조회한다.

- `dw_operations.content_usage`
- `dw_personalization.content_usage`
- `dm_operations.daily_usage_segment`
- `dm_personalization.customer_daily_usage`

정상 기준은 네 결과 모두 `difference_mb = 0`, `total_check = PASS`다.
`NO_USAGE_DATA`는 네 테이블 모두 비어 있다는 뜻이다. 초기화만 완료된 상태에서는 가능하지만,
사용량 적재를 기대했다면 실행 이력과 워터마크를 다시 확인한다.

운영 DW는 카테고리 단위 집계이므로 개인화 DW와 행 수가 다른 것은 정상이다.
가입일 이전 사용량은 적재 대상에서 제외되므로 S3 원본 행 수와 직접 비교하지 않는다.
전체 총합 일치만으로 날짜별·개별 행의 완전성까지 보장하지는 않는다.

전체 스캔은 RDS에 조회 부하를 주며 데이터가 많으면 수분 이상 걸릴 수 있다.
검증은 동일한 읽기 전용 스냅샷을 사용하므로 가급적 적재가 멈춘 뒤 실행한다.

## 오류 또는 중단 시

- 기본 조회는 SQL 문장당 30초, 전체 총합 비교는 해당 SQL 문장에 10분 제한이 있다.
  제한 초과나 오류는 검증 완료가 아니라 검증 중단이다.
- 이 파일 실행 중 오류가 나거나 조회를 취소해서 트랜잭션이 남았다면 다음을 실행한다.

```sql
rollback;
```

이는 검증 파일이 연 읽기 전용 트랜잭션을 종료하는 명령이다.
다른 작업의 미완료 트랜잭션을 정리하는 용도로 무조건 실행하지 않는다.

권한 오류나 테이블 없음 오류가 나면 접속한 DB와 사용자의 조회 권한을 확인한다.
끝에 `Read-only report finished`가 출력돼도 보고서 조회가 끝났다는 뜻일 뿐,
모든 검증이 통과했다는 뜻은 아니다. 각 항목의 결과를 확인한다.

## 저장 위치와 배포

이 폴더는 현재 Dockerfile과 `.dockerignore` 설정상 Lambda 이미지에 포함되지 않는다.
검증 파일을 S3나 RDS에 업로드하거나 Lambda 이미지를 다시 배포할 필요는 없다.
저장소 위치를 변경했다면 `\i` 명령의 파일 경로도 수정한다.
