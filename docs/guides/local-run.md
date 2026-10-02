# 로컬 생성·적재·검증

합성 데이터를 생성해 폐기 가능한 로컬 PostgreSQL DB에 적재하는 절차입니다. 저장소 루트에서 실행하며, 실행 모드별 상세 규칙은 [파이프라인 안내](../../pipeline/README.md)를 기준으로 합니다.

## 1. 실행 환경 준비

Python과 PostgreSQL 15 이상, PATH의 `psql`이 필요합니다. 저장소 루트에 가상환경을 만들고 생성기 의존성을 설치합니다. 기존 `.venv`가 있다면 활성화부터 진행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r generator/requirements.txt
psql --version
```

전체 배치와 초기화는 기존 DW/DM 데이터를 교체합니다. 별도의 폐기 가능한 로컬 DB를 준비하고, 그 연결 문자열을 현재 세션의 `KT_ND_LOCAL_CONNECTION_STRING` 환경 변수로 제공하세요. 명령 기록·문서·커밋에 실제 인증 정보를 남기지 않습니다. 아래 명령은 이 값이 준비되어 있다고 가정합니다.

## 2. 원본 CSV 생성과 검증

다음 예시는 고객 상태 기준일을 `2026-09-29`, 마지막 사용량 날짜를 전날로 고정합니다. 기본 출력 폴더를 사용하므로 기존 생성 파일을 교체할 수 있습니다. 현재 입력을 보관해야 하면 생성 전에 별도로 보관합니다.

전체 배치와 증분 중 사용할 방식에 맞춰 `--content-usage-layout`을 고릅니다. 처음 전체 배치를 확인할 때는 `single`을 사용합니다.

```powershell
python generator/src/kt_synthetic_data_generator.py `
  --reference-date 2026-09-29 `
  --usage-through-date 2026-09-28 `
  --content-usage-layout single `
  --no-analysis-output
python generator/scripts/check_distribution.py
```

생성기의 내부 검증과 저장된 CSV의 컬럼·관계·분포를 확인합니다. 출력 방식과 옵션은 [생성기 안내](../../generator/README.md)에 있습니다.

## 3-A. 전체 배치 실행

단일 `content_usage.csv`를 포함한 원본 CSV 14개를 사용합니다.

```powershell
.\pipeline\scripts\run_pipeline.ps1 `
  -ConnectionString $env:KT_ND_LOCAL_CONNECTION_STRING `
  -ReferenceDate "2026-09-29" `
  -AllowSyntheticDefaultKey
```

`-AllowSyntheticDefaultKey`는 로컬 합성 데이터용입니다. 다른 환경에서는 비밀 관리 도구로 `KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY`를 설정합니다.

접속된 psql에서 이번 전체 배치의 상태와 품질 결과를 확인합니다.

```sql
select batch_id, status, reference_date, started_at, ended_at
from audit.pipeline_run
where pipeline_name = 'full_snapshot'
order by started_at desc;

select r.batch_id, r.status, count(q.rule_name) as checked_rules,
       coalesce(sum(q.failed_row_count), 0) as failed_rows
from audit.pipeline_run r
left join audit.data_quality_result q on q.batch_id = r.batch_id
where r.pipeline_name = 'full_snapshot'
group by r.batch_id, r.status, r.started_at
order by r.started_at desc;
```

요청한 배치가 `SUCCEEDED`이고 `checked_rules > 0`, `failed_rows = 0`인지 확인합니다. 실패한 배치의 품질 결과는 롤백될 수 있습니다.

## 3-B. 증분 초기화와 일별 적재

이 방식은 별도의 빈 파이프라인 DB와 `daily` 또는 `both` 출력이 필요합니다. 위 생성 명령의 layout을 `daily`로 바꾸어 생성·검증하고, 동일한 기준일로 초기화합니다. 전체 배치를 수행한 DB를 계속 사용하려고 초기화를 실행하지 않습니다.

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

초기화는 사용량을 제외한 스냅샷 13개를 적재합니다. 증분은 위 처리 기준일의 전날인 `2026-09-28`까지 날짜 파티션을 순서대로 처리합니다. 후속 실행도 같은 HMAC 키를 사용하고 성공 워터마크 다음 날부터 이어 갑니다.

접속된 psql에서 [검증 도구](../../tools/README.md#적재-후-검증)를 실행합니다.

```psql
\set verify_totals false
\i C:/kt_nd/tools/verification/verify_loaded_data.psql
```

배치 상태와 품질 결과가 정상이고 워터마크가 의도한 마지막 사용량 날짜에 도달했는지 확인합니다. 초기화 직후에는 사용량 워터마크가 없는 것이 정상일 수 있습니다.

## 4. 고객 사례 조회

적재가 완료되면 [도구 안내](../../tools/README.md#추천-시연용-고객-선정)의 조건과 권한을 확인하고 사례별 SQL을 실행합니다. 최근 30일 사례는 30일 모두 관측된 고객만 포함하므로 적재 기간이 짧거나 가입일이 최근이면 결과가 없을 수 있습니다.

AWS 입력으로 옮기려면 [AWS 배포 가이드](aws-deployment.md)를 사용합니다. 이미 적재한 날짜의 원본 변경은 [파이프라인 정정 절차](../../pipeline/README.md#날짜와-재실행-규칙)를 따릅니다.
