# AWS 실행과 컨테이너 배포

로컬 파이프라인을 AWS Lambda에서 실행할 수 있도록 S3 입력과 Secrets Manager를 연결하고, 실행 도구를 Docker 이미지에 담습니다. 한 Lambda가 운영·개인화 DW/DM을 함께 처리합니다.

## 입력과 결과

Handler는 실행 이벤트와 환경 설정을 받아 필요한 S3 파일을 임시 디렉터리에 다운로드합니다. Secrets Manager에서 DB 인증 정보와 HMAC 키를 읽어 PowerShell 실행기의 환경에 전달한 뒤 배치 상태와 품질 결과를 확인합니다.

DB에 데이터를 적재하는 action은 `initialize`, `incremental`, `correction`입니다. `health`는 설치 환경만, `check`는 DB 연결·원본 파일 존재를 읽기 전용으로 확인합니다. 이미지 빌드나 ECR 업로드만으로 DB 적재나 Lambda 이미지 갱신이 실행되지는 않습니다.

## 폴더 구성

| 경로 | 역할 |
| --- | --- |
| [lambda/handler.py](lambda/handler.py) | 이벤트 검증, 다운로드·비밀 조회, 기존 파이프라인 호출, audit 검증 |
| [lambda/test_handler.py](lambda/test_handler.py) | AWS·네트워크·DB를 호출하지 않는 unittest |
| [docker/Dockerfile](docker/Dockerfile) | Lambda 실행 도구와 DB·파이프라인 코드를 포함하는 이미지 |
| [루트 .dockerignore](../.dockerignore) | 이미지 빌드에 필요한 파일만 허용 |
| [GitHub Actions](../.github/workflows/push-ecr.yml) | 테스트 → 이미지 빌드 → 컨테이너 검사 → main의 ECR 업로드 |

이미지에는 Lambda Python 3.12, PowerShell 7.6.6, PostgreSQL 18 클라이언트, 공개 RDS CA 인증서, `db/`, `pipeline/`, Handler를 넣습니다. AL2023 패키지 저장소 버전은 Dockerfile에 고정되어 있습니다. 생성기·생성 CSV·도구·Git 이력·로컬 인증 파일은 이미지에 넣지 않습니다.

운영 고객·월 집계 뷰의 [130 마이그레이션](../db/schema/130_install_operations_monthly_preagg_view.sql)도
db/와 함께 이미지에 포함됩니다. Lambda가 호출하는 015 초기화·020 증분/정정 SQL에서
060·070·080 이후 새 뷰와 운영 조회 권한을 적용합니다. 전체 010 SQL도 같은 정의를 적용합니다.
Handler와 Dockerfile은 기존 디렉터리 복사·파이프라인 호출을 그대로 사용합니다.

스키마 변경을 실행 경로에 적용하려면 변경된 이미지로 Lambda를 재배포해야 합니다.
health·check는 DDL을 실행하지 않으며 ALREADY_PROCESSED로 종료된 요청도 적용하지 않습니다.
기존 DB에 뷰만 먼저 적용하려면 데이터 초기화 대신 관리자 psql의
[130 스키마 파일](../db/schema/130_install_operations_monthly_preagg_view.sql)을
[DB 적용 안내](../db/README.md#운영-고객월-선집계-뷰-적용)에 따라 트랜잭션에서 적용합니다.
n8n의 002·005 카탈로그 입력은 별도로 갱신합니다.

## Lambda 설정

| 환경 변수 | 의미와 예시 |
| --- | --- |
| `S3_BUCKET` | 실제 버킷 이름. `s3://` 제외 |
| `MASTER_PREFIX` | 스냅샷 CSV 13개가 있는 prefix. 예: `kt-nd/master` |
| `CONTENT_USAGE_PREFIX` | 일별 사용량 prefix. 예: `kt-nd/raw/content_usage` |
| `RDS_SECRET_ID` | DB 인증 Secret ID. 예: `kt-nd/rds/admin` |
| `PSEUDONYMIZATION_SECRET_ID` | HMAC 키 Secret ID. 예: `kt-nd/pipeline/pseudonymization` |
| `DATABASE_NAME` | 적재 대상 DB 이름 |
| `CONTENT_USAGE_START_DATE` | 일별 원본의 최초 날짜. 예: `2025-10-24` |
| `RDS_CA_PATH` | 이미지의 공개 CA 경로. 기본 `/opt/certs/global-bundle.pem` |

RDS Secret JSON에는 `host`, `port`, `username`, `password`가 필요합니다. HMAC Secret JSON에는 `pseudonymization_key`가 필요하며 합성 기본키가 아닌 32자 이상의 안정된 값을 사용합니다. DB 이름은 Secret의 optional `dbname` 대신 `DATABASE_NAME`을 사용합니다.

실제 비밀번호와 키는 환경 변수 값이나 파일에 직접 저장하지 않습니다. 실행 중 자식 프로세스 환경으로 전달하고 응답·로그에 기록하지 않습니다. 초기화부터 이후 배치까지 같은 HMAC 키를 유지합니다.

## 로컬 검증

저장소 루트에서 실행합니다.

```powershell
python -B -m unittest discover -s deploy/lambda -p "test_handler.py" -v
```

Docker가 준비되어 있다면 저장소 루트를 빌드 컨텍스트로 유지합니다.

```powershell
docker build --platform linux/amd64 --provenance=false `
  -f deploy/docker/Dockerfile -t kt-nd-pipeline:local .
docker run --rm --network none --read-only --user 1000:1000 `
  --tmpfs /tmp:rw,nosuid,size=512m,mode=1777 `
  --entrypoint /var/lang/bin/python kt-nd-pipeline:local `
  -c 'import json, handler; result = handler.lambda_handler({"action": "health"}, None); assert result["status"] == "SUCCEEDED"; print(json.dumps(result))'
```

health는 AWS API와 DB에 접근하지 않습니다. 오프라인 테스트와 health는 실제 네트워크·데이터 품질·처리 시간 검증을 대신하지 않습니다.

## AWS에서 실행하기

[배포 가이드](../docs/guides/aws-deployment.md)의 순서대로 ECR 이미지, Lambda, 네트워크와 권한을 준비하고 `health → check → initialize → incremental`을 수동 실행합니다. 기존 사용량 정정은 `correction`을 사용합니다.

Lambda 요청은 1~7일 증분 또는 이미 적재한 1일 정정입니다. 이미 데이터가 있는 DB의 초기화는 Handler가 거절합니다. 상세 날짜·재실행 규칙은 [파이프라인](../pipeline/README.md#날짜와-재실행-규칙)에 있습니다.

ECR의 `latest` 태그를 갱신해도 기존 Lambda는 자동으로 새 digest를 사용하지 않습니다. 사용자가 새 이미지를 배포해야 합니다. 실행 결과는 [검증 도구](../tools/README.md#적재-후-검증)로 확인합니다.
