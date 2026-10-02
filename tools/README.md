# 조회·검증 도구

적재된 데이터를 읽기 전용으로 확인하고 추천 시연에 사용할 합성 고객을 찾는 SQL 도구입니다. 파이프라인 품질 검사는 배치 안에서 수행하며, 이 도구는 실행이 끝난 뒤 저장된 결과를 확인할 때 사용합니다.

## 도구 선택

| 경로 | 목적 | 입력과 결과 |
| --- | --- | --- |
| `verification/verify_loaded_data.psql` | 증분 파이프라인 성공 여부 확인 | DB 실행 이력·워터마크·품질 결과와 선택적 사용량 총합 보고서 |
| `customer-selection/*.sql` | 추천 사례 고객 선정 | 고객 현재 상태·최근 사용량·정책에서 최대 10명의 고객 조회 |

아래 명령은 연결된 psql에서 실행합니다. 고객 선정 SQL은 DB가 연결된 SQL 편집기에서도 실행할 수 있습니다. 실제 연결 문자열과 키는 파일에 기록하지 않습니다.

- [적재 후 검증](#적재-후-검증): 성공 상태와 적재 종료일 확인
- [추천 시연용 고객 선정](#추천-시연용-고객-선정): 사례 조건과 결과 해석

## 적재 후 검증

[verify_loaded_data.psql](verification/verify_loaded_data.psql)은 `content_usage_daily` 파이프라인의
실행 이력, 워터마크, 기록된 품질 결과와 선택적인 DW/DM 사용량 총합을 조회한다.
로컬 파일의 SQL을 연결된 PostgreSQL에서 실행하며 데이터·스키마·audit 기록을 변경하지 않는다.

### 실행 전 준비

1. Lambda 적재 호출이 종료됐는지 CloudWatch 로그의 동일 RequestId에 대한 `REPORT`로 확인한다.
   호출 종료와 적재 성공은 다르므로 성공 여부는 검증 결과도 확인한다.
2. 기존에 사용하던 접속 명령으로 로컬 `psql`에서 대상 RDS 데이터베이스에 접속한다.
   연결 문자열·비밀번호·키는 이 문서나 검증 파일에 저장하지 않는다.
3. 기존 트랜잭션이 없는 세션에서 실행한다. 다른 작업의 트랜잭션이 열려 있다면
   먼저 해당 작업을 처리하거나 새 `psql` 세션으로 접속한다.

아래 `\i`, `\set` 명령은 PowerShell이 아니라 **접속된 psql 프롬프트**에서 실행한다.
검증 파일의 절대 경로를 사용하므로 PowerShell의 현재 폴더는 상관없다.

### 기본 검증 실행

```psql
\set verify_totals false
\i C:/kt_nd/tools/verification/verify_loaded_data.psql
```

기본 실행은 다음 세 항목을 조회한다. 전체 사용량 테이블은 스캔하지 않는다.

#### 1. 최근 실행 이력

최근 10개 배치의 상태와 처리 날짜를 표시한다.

- 완료하려던 최신 배치가 `SUCCEEDED`인지 확인한다.
- 오류 해결 과정에서 남은 과거 `FAILED` 이력 자체는 현재 데이터의 실패를 뜻하지 않는다.
- `RUNNING` 이력은 실제 Lambda가 아직 실행 중이라는 증거가 아니다.
  타임아웃 등으로 상태가 남을 수 있으므로 CloudWatch 로그로 확인한다.

#### 2. 워터마크

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

#### 3. 기록된 품질 결과

성공한 모든 배치에서 아래 조건을 확인한다.

- `checked_rules > 0`
- `failed_rows = 0`
- `recorded_quality_check = PASS`

`MISSING_QUALITY_RESULTS`는 성공 배치에 품질 결과가 없다는 뜻이다.
조회 결과가 0행이면 성공 배치가 없는 것이므로 검증 통과로 해석하지 않는다.

이 항목은 저장된 결과를 조회할 뿐 기존 품질 SQL을 재실행하지 않는다.
모든 개별 규칙이 빠짐없이 실행됐는지까지 증명하지는 않는다.
실패 배치의 품질 기록은 롤백될 수 있어, 실패 결과가 없다는 사실만으로 성공을 판단하면 안 된다.

### 선택: 전체 DW/DM 사용량 총합 비교

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

### 오류 또는 중단 시

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

### 저장 위치와 배포

도구 폴더는 Dockerfile과 `.dockerignore` 설정상 Lambda 이미지에 포함되지 않는다.
검증 파일을 S3나 RDS에 업로드하거나 Lambda 이미지를 다시 배포할 필요는 없다.
저장소 위치를 변경했다면 `\i` 명령의 파일 경로도 수정한다.

## 추천 시연용 고객 선정

추천 시연에 사용할 합성 고객을 사례별로 선정하는 PostgreSQL 조회 쿼리입니다.
가족결합은 4-A 프리미엄 가족결합과 4-B 총액결합으로 나누어 조회합니다.
각 기본 쿼리는 독립적으로 실행하며 최대 10명의 `user_id`와 `name`을 반환합니다.

### 선정 기준과 실행 조건

| 사례 | 선정 기준 |
| --- | --- |
| 1. YouTube 사용과 혜택 불일치 | 최근 30일 YouTube 사용량 20GB 이상, 전체 사용량의 30% 이상, YouTube 서비스 미선택 |
| 2. 고사용량·저가 요금제 | 최근 30일 사용량 80GB 이상, 월정액 61,000원 이하, 기본 데이터 30GB 이하 |
| 3. 저사용량·고가 요금제 | 최근 30일 사용량 15GB 미만, 월정액 80,000원 이상 |
| 4-A. 프리미엄 가족결합 미가입 | 프리미엄 가족결합 조건을 충족하는 미결합 가족의 초이스 고객 중 베이스 후보 외 고가 회선 |
| 4-B. 총액결합 미가입 | 가족 구성원 2명 이상인 미결합 가족 중 정책표상 모바일 총액결합 할인액이 양수인 가족의 고객 |

- 사용량 기준은 예시 선정을 위한 값입니다. 각 쿼리의 `where` 조건과 `limit 10`을 조정할 수 있습니다.
- 사례 1~3은 최신 적재일을 종료일로 하는 최근 30일을 사용합니다. 30일 모두 관측된 고객만 포함하며, 사용량이 없는 날짜는 0으로 보충하지 않습니다.
- 사용량은 MB 합계를 1024로 나눈 GB입니다. YouTube 사용량은 시청시간이 아니라 `youtube_video`, `youtube_shorts`, `youtube_music`의 데이터 사용량입니다.
- 요금은 할인 전 월정액입니다. 현재 요금제·서비스·할인 상태를 조회하며 과거 상태를 재현하지 않습니다.
- 사례 1~3은 `ai_personalization` 조회 권한이 필요합니다. 사례 4-A와 4-B는 추가로 `dw_personalization` 조회 권한이 필요하며, 기본 `n8n_personalization` 역할에는 DW 직접 조회 권한이 없습니다.
- 사례 4의 정책 유효기간은 실행일(`current_date`) 기준입니다. 과거 정책을 검토할 때는 해당 표현식을 명시적인 기준일로 변경합니다.
- 가족 사례의 `limit 10`은 가족 10개가 아니라 고객 10명입니다. 같은 가족의 고객이 여러 행에 나올 수 있습니다.
- 이 문서는 수동 예시 선정용이며 [n8n 고정 쿼리 계약](../docs/integration/n8n-fixed-query-contract.md)의 등록 카탈로그에 추가된 쿼리는 아닙니다.
- 저장소 스키마와 정책 마스터를 기준으로 작성했습니다. 실제 DB 실행과 사례별 추출 건수는 아직 검증하지 않았습니다.

### SQL 파일 실행 방법

실행할 사례의 `.sql` 파일을 SQL 편집기에서 열어 해당 DB 연결로 실행합니다.
파일은 `tools/customer-selection/`에 있으며 사례별로 독립 실행합니다.
사용량·요금 기준과 고객 수를 바꿀 때는 SQL 파일을 수정합니다.

접속된 psql 프롬프트에서도 다음처럼 선택한 파일을 실행할 수 있습니다.
아래는 PowerShell 명령이 아니라 psql 명령이며, 저장소를 옮겼다면 경로를 수정합니다.

```psql
\i C:/kt_nd/tools/customer-selection/case_01_youtube_benefit_mismatch.sql
```

### 1. YouTube 사용량이 많지만 YouTube 혜택을 선택하지 않은 고객

현재 요금제에서 YouTube 혜택을 선택할 수 있지만 미선택한 고객과, 현재 요금제에
YouTube 혜택이 없는 고객을 `case_detail`로 구분합니다.
저장소 마스터에서는 `S002`가 `YouTube Premium Lite`입니다.

조회 SQL: [case_01_youtube_benefit_mismatch.sql](customer-selection/case_01_youtube_benefit_mismatch.sql)

#### 초이스 미만의 7만~8만 원대 무제한 고객만 선정

사례 1 SQL 파일에서 마지막 `where`와 `order by` 사이에 있는 옵션 조건 다섯 줄의 주석을 해제합니다.
저장소 기준으로 `베이직80`은 월 80,000원 무제한이고, `초이스90`부터 YouTube 선택 혜택을 제공합니다.

서비스 미선택은 저장소에 기록된 요금제 혜택 선택 상태입니다. 외부에서 별도로 구매한
YouTube 구독 여부는 이 데이터로 판단하지 않습니다.

### 2. 데이터 사용량이 많지만 저가 요금제를 이용하는 고객

조회 SQL: [case_02_high_usage_low_fee.sql](customer-selection/case_02_high_usage_low_fee.sql)

`base_data_limit_gb`는 기본 제공량입니다. 연령별 추가 데이터와 이월량은 반영하지 않았으므로
실제 초과 사용 여부나 추가 요금 발생을 확정하는 쿼리는 아닙니다.

### 3. 데이터 사용량이 적지만 고가 요금제를 이용하는 고객

조회 SQL: [case_03_low_usage_high_fee.sql](customer-selection/case_03_low_usage_high_fee.sql)

요금제 하향 검토용 예시입니다. 사용량 외 부가서비스, 공유 데이터, 할인 등의 가치는 별도로 확인합니다.

### 4-A. 프리미엄 가족결합 할인을 받지 못하는 초이스 고객

저장소의 `D003` 정책은 추가 고가 회선에 대한 25% 할인입니다. 초이스 요금제 이용만으로
할인 자격이 결정되지 않으며, 현재 정책 마스터의 조건은 다음과 같습니다.

- 정상 이용 중인 KT 인터넷과 `BASIC_ESSENCE_PREMIUM` 인터넷 상품 그룹
- 월정액 77,000원 이상 모바일 회선 2개 이상
- 모바일 회선 10개 이하
- 베이스 회선 1개를 제외한 추가 고가 회선

가족 전체 고가 회선에서 베이스 후보를 먼저 선정하고, 나머지 회선 중 초이스 고객을 추출합니다.
베이스 후보 선정 순서는 생성기와 같은 월정액 오름차순 → 나이 내림차순 → 가입일 오름차순이며,
동률이면 `user_id`로 정렬합니다. 초이스 외 고가 회선도 가족의 자격과 베이스 후보 판단에 포함합니다.

조회 SQL: [case_04a_premium_family_not_enrolled.sql](customer-selection/case_04a_premium_family_not_enrolled.sql)

`potential_premium_discount_per_month`는 해당 고객을 추가 고가 회선으로 결합했을 때의
월 할인 후보 금액입니다. 베이스 회선 지정에 따라 대상이 달라질 수 있습니다.
청소년 추가 혜택(`D004`)은 이 사례의 선정 대상이 아닙니다.

### 4-B. 총액결합 할인을 받지 못하는 고객

미결합 가족의 모바일 월정액 합계, 인터넷 상품 그룹, 약정기간을 정책표에 대입합니다.
`D001` 모바일 총액결합 할인 풀이 0원보다 큰 가족의 고객을 추출합니다.

조회 SQL: [case_04b_total_bundle_not_enrolled.sql](customer-selection/case_04b_total_bundle_not_enrolled.sql)

`potential_family_mobile_discount`는 가족 전체 모바일 할인 풀입니다. 고객 행마다 표시되므로
이 컬럼을 고객별로 합산하면 같은 가족의 할인액이 중복됩니다. 개인별 금액은 균등·기여도 등
배분 방식에 따라 달라지며, 인터넷 회선 할인(`D005`)은 이 금액에 포함하지 않습니다.

4-A와 4-B에는 같은 가족이 나올 수 있습니다. 4-B의 금액은 가족의 참여 가능 모바일 전체를
합산한 일반 총액결합 시나리오입니다. 프리미엄 가족결합을 적용할 때는 베이스·저가 회선만
총액결합 계산에 포함하므로, 두 쿼리의 할인 후보 금액을 그대로 더하지 않습니다.

### 관련 기준 문서

- [개인화 뷰와 권한](../db/schema/060_ai_views_roles.sql)
- [개인화 DW 스키마](../db/schema/030_dw_personalization.sql)
- [원본 데이터 스키마와 할인 계산 기준](../docs/data/raw-data-schema.md)
- [합성 데이터 생성기](../generator/src/kt_synthetic_data_generator.py)
