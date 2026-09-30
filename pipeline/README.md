# Pipeline

이 폴더는 나중에 실제 연결·적재할 때 사용할 실행 순서만 정의합니다. 저장소 변경만으로는
DB나 RDS에 접속하지 않으며 CSV도 적재하지 않습니다.

| 모드 | 입력 | 진입점 |
| --- | --- | --- |
| 전체 배치 | 스냅샷 CSV 13개와 `content_usage.csv` | `scripts/run_pipeline.ps1` |
| 증분 초기화 | 사용량을 제외한 스냅샷 CSV 13개 | `scripts/initialize_incremental_pipeline.ps1` |
| 일별 증분/정정 | 날짜별 content usage 파티션 | `scripts/run_incremental_pipeline.ps1` |

모든 경로는 같은 advisory lock을 사용합니다. 원본은 `pg_temp` staging에만 머물고 운영
DW에는 HMAC 가명 키만 저장됩니다. 증분 배치는 1~7일 단위이며 정정 시 해당 월의 일/월
집계를 다시 계산합니다. 전체·증분 적재 모두 가입일 당일부터의 사용량만 DW에 반영하며,
가입일 이전 원본 행은 변경하지 않고 적재 대상에서 제외합니다.

운영과 개인화 n8n workflow는 각각 `n8n_operations`, `n8n_personalization` 계정을 사용합니다.
비밀번호는 저장소가 아니라 배포 환경의 비밀 관리 도구에서 설정합니다.
