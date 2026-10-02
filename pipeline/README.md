# 데이터 파이프라인

생성된 CSV를 PostgreSQL에 적재하고 운영·개인화 DW/DM을 갱신하는 실행 진입점입니다. [DB 폴더](../db/README.md)의 SQL을 정해진 순서로 호출하고, 배치 ID·원본 checksum·트랜잭션·품질 결과와 마지막 성공 날짜를 관리합니다.

## 입력과 결과

입력은 CSV와 DB 연결 설정, 기준일, HMAC 가명화 키입니다. 결과는 두 영역의 DW/DM 데이터와 `audit` 실행 이력입니다. 워터마크는 사용량 적재가 성공한 마지막 날짜로, 다음 증분이 어디부터 시작해야 하는지 알려 줍니다.

두 영역은 같은 배치 트랜잭션과 `content_usage_daily` advisory lock을 사용하고, 해당 이름의 워터마크를 공유합니다. 한 영역의 변환이나 품질 검사에 실패하면 배치 데이터는 함께 롤백됩니다. 스키마 DDL은 배치 적재 트랜잭션보다 먼저 실행됩니다.

## 어떤 실행 모드를 사용하나요?

| 모드 | 입력 | 목적 | PowerShell → psql |
| --- | --- | --- | --- |
| 전체 배치 | 스냅샷 13개와 단일 `content_usage.csv` | 전체 DW/DM 교체 | `run_pipeline.ps1` → `010_run_pipeline.psql` |
| 증분 초기화 | 사용량을 제외한 스냅샷 13개 | 빈 DB에 고객·정책 기준 데이터 준비 | `initialize_incremental_pipeline.ps1` → `015_initialize_incremental_pipeline.psql` |
| 일별 증분 | 날짜별 `part-*.csv` | 성공한 마지막 날짜 뒤의 사용량 추가 | `run_incremental_pipeline.ps1` → `020_run_incremental_pipeline.psql` |
| 원본 정정 | 특정 날짜의 `run_id` 파티션 | 이미 적재한 날짜를 새 원본으로 교체 | 같은 증분 실행기에 정정 옵션 전달 |

전체 배치와 초기화 SQL은 DW/DM을 truncate하므로 기존 데이터를 교체합니다. 증분 초기화는 빈 파이프라인 DB를 준비할 때 사용합니다. Lambda Handler는 기존 데이터가 있으면 초기화를 거절하지만, 로컬 초기화 실행기에는 같은 사전 차단이 없으므로 대상 DB를 확인해야 합니다.

## 폴더 구성과 실행 순서

- `scripts/`: 입력 파일·checksum·날짜 확인과 psql 호출을 담당하는 PowerShell 실행기
- `sql/`: DB SQL 참조, 배치 트랜잭션과 성공 상태 저장을 담당하는 psql 진입점

1. DB 스키마, AI View·역할과 마이그레이션을 적용합니다.
2. 배치 상태를 시작하고 CSV를 `pg_temp.stg_*`에 읽습니다.
3. 원본 관계·값 품질을 검사합니다.
4. 운영·개인화 DW를 적재하고 DM을 구성하거나 갱신합니다.
5. 두 영역의 DW/DM 품질 검사를 수행합니다.
6. 성공 상태와 필요한 워터마크 갱신을 커밋합니다.

가입일 이전 사용량은 원본에서 삭제하지 않고 DW 적재 대상에서 제외합니다. 운영 DW는 이름을 제외하고 연결 키를 가명화하며 개인화 DW는 원본 사용자 ID·이름·상세 사용량을 유지합니다.

## 로컬 실행

PostgreSQL 15 이상과 PATH의 `psql`이 필요합니다. 연결 문자열과 키는 환경의 비밀 설정으로 전달하고 파일·로그·Git에 저장하지 않습니다. 아래 명령은 준비된 세션의 `$env:KT_ND_LOCAL_CONNECTION_STRING`을 사용합니다.

전체 배치:

```powershell
.\pipeline\scripts\run_pipeline.ps1 `
  -ConnectionString $env:KT_ND_LOCAL_CONNECTION_STRING `
  -ReferenceDate "2026-09-29" `
  -AllowSyntheticDefaultKey
```

증분 초기화 후 지정한 처리일까지 적재:

```powershell
.\pipeline\scripts\initialize_incremental_pipeline.ps1 `
  -ConnectionString $env:KT_ND_LOCAL_CONNECTION_STRING `
  -ReferenceDate "2026-09-29" `
  -AllowSyntheticDefaultKey
.\pipeline\scripts\run_incremental_pipeline.ps1 `
  -ConnectionString $env:KT_ND_LOCAL_CONNECTION_STRING `
  -ProcessingDate "2026-09-29" `
  -AllowSyntheticDefaultKey
```

`-AllowSyntheticDefaultKey`는 폐기 가능한 로컬 합성 데이터에만 사용합니다. 다른 환경은 `KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY`를 설정합니다. 초기화와 이후 배치는 같은 키를 유지해야 합니다.

환경 준비와 데이터 생성부터 이어 실행하려면 [로컬 실행 가이드](../docs/guides/local-run.md)를 따릅니다. AWS에서는 [배포 모듈](../deploy/README.md)의 Handler가 동일한 실행기를 호출합니다.

## 실행 옵션

| 옵션 | 사용하는 모드와 의미 |
| --- | --- |
| `ConnectionString` | 모든 모드의 필수 DB 연결 설정 |
| `RawDirectory` | 전체·초기화의 CSV 폴더. 기본 `generator/data/generated/` |
| `ReferenceDate` | 전체·초기화의 고객 상태 기준일. 생략 시 오늘(KST) |
| `ContentRoot` | 증분의 파티션 루트. 기본 `generator/data/generated/raw/content_usage/` |
| `ProcessingDate` | 증분 처리 기준일. 적재 상한은 전날이며 기본값은 오늘(KST) |
| `MaxDatesPerBatch` | 증분 배치당 날짜 수. 기본 7일, 허용 1~31일 |
| `CorrectionDate`, `CorrectionVersion` | 함께 지정하는 정정 날짜와 `run_id` |
| `PseudonymizationKey` | 모든 모드의 HMAC 키. 환경 변수로 전달하는 방식을 권장 |

## 날짜와 재실행 규칙

신규 증분은 워터마크 다음 날부터 `ProcessingDate - 1일`까지 연속된 파티션이 필요합니다. 첫 증분은 워터마크가 없으므로 입력에서 가장 이른 적재 가능 날짜부터 시작합니다. 날짜가 누락되면 실패합니다. 처음에는 짧은 범위를 처리해 실행 시간을 확인합니다.

Lambda는 1~7일의 신규 증분만 허용하고 오늘(KST)과 미래 날짜를 차단합니다. 요청 종료일 다음 날을 `ProcessingDate`로 전달하며 실행기의 배치 크기를 7일로 지정합니다. 정정은 오늘(KST)을 처리 기준일로 사용합니다.

| 실행 경로 | 같은 입력을 다시 실행하면 |
| --- | --- |
| 전체 배치 SQL | checksum이 같아도 DW/DM 전체를 다시 교체 |
| 초기화·증분/정정 SQL | 성공한 같은 checksum이면 no-op |
| 로컬 신규 증분 실행기 | 성공 워터마크 이후 날짜만 처리 |
| Lambda 신규 증분 | 범위 전체가 워터마크에 포함되면 `ALREADY_PROCESSED` |

`ALREADY_PROCESSED`는 기존 원본 checksum 재검증을 의미하지 않습니다. 기존 날짜의 원본 변경은 correction을 사용합니다.

정정 파일은 `event_date=YYYY-MM-DD/run_id=VERSION/part-*.csv`에 둡니다. 정정 날짜는 성공 워터마크와 처리 상한을 모두 넘을 수 없습니다. 해당 날짜의 DW 데이터를 교체하고 영향받은 월의 일·월 집계를 다시 계산합니다.

```powershell
.\pipeline\scripts\run_incremental_pipeline.ps1 `
  -ConnectionString $env:KT_ND_LOCAL_CONNECTION_STRING `
  -CorrectionDate "2026-09-28" `
  -CorrectionVersion "fix-001" `
  -AllowSyntheticDefaultKey
```

현재 요금제 상태는 기준일 스냅샷이며 과거 상태를 재현하지 않습니다. 데이터 종료 뒤 DB를 폐기하는 합성 프로젝트 전제라 별도 장기 stale 정책은 두지 않습니다.

## 성공 확인과 스키마 변경

요청한 배치의 `audit.pipeline_run.status = 'SUCCEEDED'`, 품질 검사 기록과 실패 행 0개를 확인합니다. 증분은 워터마크가 의도한 종료일까지 도달했는지도 확인합니다. 초기화만 성공한 DB에는 사용량 워터마크가 없을 수 있습니다.

[도구 사용 안내](../tools/README.md)의 검증 SQL은 `content_usage_daily` 초기화·증분 경로를 조회합니다. 전체 배치 이력은 `pipeline_name = 'full_snapshot'`으로 별도 확인해야 합니다. 품질 실패 기록이 롤백될 수 있어 실패 행이 없다는 사실만으로 성공으로 판단하지 않습니다.

마이그레이션과 staging 타입 처리는 [DB 안내](../db/README.md#타입과-마이그레이션에서-주의할-점)에 정리되어 있습니다. 기존 데이터가 있는 DB를 마이그레이션하려고 초기화를 실행하지 않습니다.
