# KT Mobile Synthetic Data Generator

KT 모바일 요금제, 사용량, 혜택과 결합 데이터를 합성해 로컬 Data Lake용 CSV를 만드는 생성기입니다. 실제 고객 정보나 실제 청구 데이터를 사용하지 않습니다.

## 역할

- 같은 옵션과 난수 시드에서 재현 가능한 합성 데이터를 생성합니다.
- 원본 성격의 CSV를 `data/generated/`에 저장합니다.
- 선택적으로 가명화된 분석용 CSV를 `data/generated_analysis/`에 저장합니다.
- PK·FK, 정책 조건, 사용량 합계와 주요 분포를 검증합니다.

파이프라인은 `data/generated/`의 원본 CSV를 PostgreSQL `landing.raw_*`에 적재해 운영·개인화 DW/DM을 생성합니다. `generator/data/`는 재생성 가능한 출력이므로 Git에서 제외합니다.

## 기본 생성 범위

| 항목 | 기본값 |
| --- | ---: |
| 사용자 수 | 1,000명 |
| 사용 기간 | 90일 |
| 난수 시드 | 3 |
| 의도적 비최적 요금제 비율 | 20% |
| CSV 수 | 14개 |

생성되는 CSV는 다음과 같습니다.

```text
users, families, bundle_discount_compositions,
plans, age_benefits, plan_age_benefits,
additional_services, plan_benefits,
discounts, internet_bundle_discount_rules, premium_family_discount_rules,
user_discounts, user_services, content_usage
```

## 실행 방법

`generator` 폴더에서 실행합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/kt_synthetic_data_generator.py
python scripts/check_distribution.py
```

원본 CSV만 생성하려면 다음 옵션을 사용합니다.

```powershell
python src/kt_synthetic_data_generator.py --no-analysis-output
```

주요 옵션:

| 옵션 | 의미 |
| --- | --- |
| `--n-users` | 생성할 사용자 수. 최소 10명 |
| `--n-days` | 사용자별 사용량 생성 일수 |
| `--seed` | 재현용 난수 시드 |
| `--suboptimal-ratio` | 의도적 비최적 요금제 사용자 비율 |
| `--output-dir` | 원본 CSV 출력 경로 |
| `--analysis-output-dir` | 가명화 분석 CSV 출력 경로 |
| `--no-analysis-output` | 가명화 분석 CSV를 생성하지 않음 |
| `--no-save` | 생성·검증만 수행하고 CSV를 저장하지 않음 |

## 문서

- [생성 기준과 합성 가정](docs/generation-spec.md)
- [원본 데이터 스키마](docs/data-schema.md)
- [가명화 분석용 데이터 스키마](docs/analysis-data-schema.md)

상세 사양에는 연령·가족·사용량 분포, 요금제 배정, 할인·결합 정책과 검증 기준이 정리되어 있습니다.