# Project Documentation

프로젝트 설계 근거와 협업 문서를 관리합니다. 실행 방법과 테이블 구현은 각 모듈 README를 기준으로 하며, 이 폴더는 왜 그렇게 설계했는지를 기록합니다.

## 현재 기준 문서

| 문서 | 내용 |
| --- | --- |
| [목표 데이터 아키텍처](architecture/target-data-architecture.md) | 확정 DW/DM, 이름 처리, 권한, 공개 RDS 기준 |
| [n8n 고정 쿼리 계약](integration/n8n-fixed-query-contract.md) | AI query ID 선택과 n8n 실행 규칙 |
| [운영 쿼리 카탈로그](query-catalogs/operations-query-catalog.csv) | 운영 workflow가 실행할 고정 SQL |
| [개인화 쿼리 카탈로그](query-catalogs/personalization-query-catalog.csv) | 개인화 workflow가 실행할 고정 SQL |
| [예시 고객 선정 쿼리](customer-selection.md) | YouTube 혜택, 사용량·요금제 불일치, 프리미엄 가족결합·총액결합 사례 고객 선정 |

## Git 추적 기준

다른 환경에서도 설계와 파이프라인을 재현하는 데 필요한 현재 기준 문서는 Git에 포함합니다.

- `architecture/`: 현재 데이터 아키텍처
- `integration/`: n8n 연동 계약
- `query-catalogs/`: 운영·개인화 고정 쿼리 카탈로그
- `customer-selection.md`: 추천 시연용 예시 고객 선정 기준, SQL 파일 링크와 실행 방법
- `../tools/customer-selection/`: 사례별로 독립 실행하는 고객 선정 SQL
- `../generator/docs/`: CSV 생성 기준과 데이터 스키마

다음 항목은 로컬 참고 자료 또는 재생성 가능한 산출물이므로 Git에 포함하지 않습니다.

- `archive/`: 현재 구현 이전의 문서 초안과 생성 DOCX
- `tools/`: 보관 DOCX 전용 생성 도구
- `../generator/data/`: 생성 CSV
- `../generator/archive/`: 생성 데이터 로컬 보관본

가상 환경, 캐시, 비밀 설정 파일과 IDE 설정도 저장소 루트의 `.gitignore`에 따라 제외합니다.

세부 테이블과 실행 순서는 [`db/README.md`](../db/README.md)와
[`pipeline/README.md`](../pipeline/README.md)를 기준으로 합니다.
