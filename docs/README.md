# 프로젝트 문서

프로젝트 전체 설계와 데이터 정의, 외부 연동 계약, 실행 절차를 모아 둡니다. 각 모듈의 역할과 주요 파일은 해당 폴더 README에서 설명하고, 이곳에서는 여러 모듈을 연결하는 설계와 상세 명세를 확인합니다.

## 읽는 목적에 따라 선택하기

| 알고 싶은 내용 | 읽을 문서 |
| --- | --- |
| 발표용 작업 범위·주요 작업·해결한 이슈 | [프로젝트 발표 정리](presentation.md) |
| 전체 데이터 흐름과 운영·개인화 분리 이유 | [데이터 아키텍처](architecture.md) |
| 처음부터 로컬에서 생성·적재·검증하기 | [로컬 실행 가이드](guides/local-run.md) |
| S3·RDS·ECR·Lambda를 연결해 실행하기 | [AWS 배포 가이드](guides/aws-deployment.md) |
| 합성 분포와 요금제·혜택·결합 생성 규칙 | [생성 상세 사양](data/generation-spec.md) |
| 원본 CSV의 컬럼·키·관계·NULL 의미 | [원본 데이터 명세](data/raw-data-schema.md) |
| 선택적 가명화 분석 CSV의 변환과 사용법 | [분석용 데이터 명세](data/analysis-data-schema.md) |
| AI가 쿼리를 선택하고 n8n이 실행하는 규칙 | [n8n 고정 쿼리 계약](integration/n8n-fixed-query-contract.md) |
| 운영 영역에서 실행할 고정 SQL | [운영 쿼리 카탈로그](integration/query-catalogs/operations-query-catalog.csv) |
| 개인화 영역에서 실행할 고정 SQL | [개인화 쿼리 카탈로그](integration/query-catalogs/personalization-query-catalog.csv) |
| AI에 전달할 운영·개인화 뷰의 컬럼·타입·집계 기준 | [AI 조회 뷰 스키마](integration/view-schemas/README.md) |
| 적재 확인과 사례별 고객 조회 | [도구 사용 안내](../tools/README.md) |
| 운영 월별 통계 쿼리의 최적화 원인과 측정 결과 | [쿼리 최적화 이슈](issues/operations-query-optimization.md) |

## 폴더 구성

- `data/`: 생성 규칙과 원본·분석용 CSV 데이터 사전
- `integration/`: n8n 실행 계약, 쿼리 카탈로그와 AI 조회 뷰 스키마
- `guides/`: 여러 모듈을 이어 실행하는 단계별 절차
- `issues/`: 해결한 이슈의 원인·적용 방법·검증 근거
- `architecture.md`: 프로젝트 전체 설계와 설계 근거
- `presentation.md`: 작업 범위와 주요 구현·이슈를 요약한 발표 문서

쿼리 카탈로그와 뷰 스키마 CSV는 생성 데이터가 아니라 관리하는 SQL 명세이므로 Git에 포함합니다. 과거 문서·DOCX와 전용 생성 도구는 `.local/archive/`에 보관하며 현재 기준 문서에서 분리합니다.

## 문서의 역할 나누기

입력·출력과 실행 옵션은 모듈 README, 컬럼과 업무 규칙은 데이터 명세, 여러 도구를 사용하는 실행 순서는 가이드에 기록합니다. 같은 규칙을 여러 문서에 복사하기보다 해당 기준 문서를 링크합니다.
