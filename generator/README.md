# 합성 통신 데이터 생성기

사용자·요금제·사용량·혜택·가족결합 데이터를 만들어 파이프라인의 입력 CSV를 준비합니다. 난수 시드와 기준일을 고정하면 같은 조건의 데이터를 재현할 수 있습니다. 실제 고객 정보는 사용하지 않습니다.

## 입력과 결과

입력은 생성할 사용자 수, 사용 기간, 기준일과 난수 시드입니다. 요금제와 정책 마스터, 연령·가족·사용량 분포 규칙은 생성기 내부에 정의되어 있습니다.

| 출력 | 용도 |
| --- | --- |
| `data/generated/` | 파이프라인 입력과 생성 결과 검증에 사용하는 원본 CSV |
| `data/generated_analysis/` | 이름을 제외하고 연결 키를 가명화한 선택적 분석 CSV |

파이프라인은 원본 CSV를 읽습니다. 분석용 CSV는 별도 분석을 위한 출력이며 DW/DM 적재에 사용하지 않습니다. 두 출력은 모두 Git에서 제외됩니다.

기본값은 사용자 1,000명, 사용 기간 90일, 난수 시드 3, 의도적 비최적 요금제 비율 20%입니다. 입력은 사용자·가족·결합 구성, 요금제·혜택·할인 정책, 고객 할인·서비스, 콘텐츠 사용량 등 14개 논리 테이블로 구성됩니다.

## 폴더 구성

| 경로 | 역할 |
| --- | --- |
| `src/kt_synthetic_data_generator.py` | 정책 마스터와 합성 규칙 적용, 검증, CSV 저장 |
| `scripts/check_distribution.py` | 저장된 원본 CSV의 컬럼·관계·분포 검증 |
| `requirements.txt` | 생성과 검증에 필요한 Python 패키지 |
| `data/` | 생성 데이터 저장 위치 |

## 생성과 검증

저장소 루트에서 Python 가상환경을 활성화하고 의존성을 설치한 뒤 실행합니다. 환경 준비부터 DB 검증까지는 [로컬 실행 가이드](../docs/guides/local-run.md)를 참고합니다.

```powershell
python generator/src/kt_synthetic_data_generator.py `
  --reference-date 2026-09-29 `
  --usage-through-date 2026-09-28 `
  --content-usage-layout single `
  --no-analysis-output
python generator/scripts/check_distribution.py
```

위 명령은 기본 출력 폴더에 파일을 저장합니다. 생성기는 내부 관계와 정책 검증을 수행하고, `check_distribution.py`는 저장된 `data/generated/`를 검증합니다. 별도 `--output-dir`로 생성한 파일은 이 검증 스크립트의 기본 대상에 포함되지 않습니다.

## 출력 방식을 고르기

| `--content-usage-layout` | 저장 방식 | 사용할 파이프라인 |
| --- | --- | --- |
| `single` | 스냅샷 13개와 단일 `content_usage.csv` | 전체 배치 |
| `daily` | 스냅샷 13개와 날짜별 사용량 파티션 | 증분 초기화 → 증분/정정 |
| `both` | 단일 파일과 날짜별 파티션을 함께 저장 | 두 방식 모두 가능 |

일별 파일 경로는 `data/generated/raw/content_usage/event_date=YYYY-MM-DD/part-000.csv`입니다. `daily`와 `--no-analysis-output`을 함께 사용하면 사용자 묶음별로 파일에 이어 쓰므로 전체 콘텐츠 사용량을 메모리에 보관하지 않습니다. 생성 규칙과 난수 순서는 단일 파일 방식과 같습니다.

## 주요 옵션

| 옵션 | 의미 |
| --- | --- |
| `--n-users`, `--n-days` | 사용자 수(최소 10명)와 사용자별 사용 기간 |
| `--reference-date` | 고객·혜택 상태의 기준일 |
| `--usage-through-date` | 마지막 사용량 날짜. 생략 시 기준일 전날 |
| `--seed`, `--suboptimal-ratio` | 재현용 난수 시드와 비최적 요금제 비율 |
| `--output-dir` | 원본 CSV 출력 위치 |
| `--content-usage-layout` | `single`, `daily`, `both` |
| `--content-user-batch-size` | 일별 스트리밍 생성의 사용자 버퍼 크기. 기본 100명 |
| `--analysis-output-dir` | 분석용 CSV 출력 위치 |
| `--no-analysis-output` | 분석용 출력 생략 |
| `--no-save` | 생성·검증만 수행하고 CSV 저장 생략 |

분석용 출력의 HMAC 키는 `KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY`로 전달할 수 있습니다. 합성 기본키와 가명화 규칙은 [생성 상세 사양](../docs/data/generation-spec.md)을 참고합니다. 고객 상태 기준일과 사용량 종료일을 분리하면 미래 날짜의 합성 파티션도 미리 만들 수 있지만, Lambda는 오늘(KST)과 미래 사용량의 적재를 허용하지 않습니다.

## 상세 문서

- [생성 규칙과 합성 분포](../docs/data/generation-spec.md)
- [원본 CSV의 컬럼과 관계](../docs/data/raw-data-schema.md)
- [가명화 분석 CSV의 변환](../docs/data/analysis-data-schema.md)
- [적재 방식과 재실행 규칙](../pipeline/README.md)
