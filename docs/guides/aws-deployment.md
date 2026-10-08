# AWS 배포와 수동 실행

S3 원본 파일과 Secrets Manager의 비밀 설정을 연결하고 Lambda 컨테이너로 파이프라인을 실행하는 절차입니다. [배포 모듈](../../deploy/README.md)은 파일 구성·설정·로컬 검증을 설명하고, 이 가이드는 AWS에서 준비하고 실행하는 순서를 설명합니다.

필요한 자원은 S3 원본 저장소, PostgreSQL RDS, ECR 저장소, Lambda 실행 역할, GitHub Actions의 AWS 인증 역할과 두 Secret입니다. 현재 배포는 운영·개인화 DW/DM을 한 Lambda에서 함께 처리합니다.

## 1. GitHub Actions에서 이미지 빌드·업로드

배포 모듈의 오프라인 테스트를 먼저 확인한 뒤 사용자가 변경을 커밋·푸시합니다. 워크플로는 `deploy/docker/Dockerfile`을 사용하고 저장소 루트를 빌드 컨텍스트로 지정합니다.

GitHub Repository variables에 다음 값을 설정합니다:

| 이름 | 값 |
| --- | --- |
| `AWS_REGION` | ECR을 만든 리전 코드 |
| `AWS_ROLE_ARN` | 이미 인증을 확인한 GitHub Actions 역할 ARN |
| `ECR_REPOSITORY` | ECR 저장소 이름만. ARN·URI가 아님 |

워크플로는 push/main, pull_request/main, workflow_dispatch로 실행합니다. PR은 오프라인
테스트와 이미지 빌드·health까지만 수행하고 AWS 인증·업로드를 건너뜁니다. main push 또는
main에서 수동 실행한 경우에만 인증 후 `latest`를 업로드합니다. Lambda 자동 배포는 하지 않습니다.

Actions → **Build and push Lambda image**의 모든 단계가 초록색인지 확인하세요.
실패하면 단계 이름과 오류 문구를 확인합니다. ECR → 프라이빗 리포지토리 → 해당 저장소 →
이미지에서 `latest`와 이미지 digest가 표시되어야 합니다. Mutable을 사용합니다.
태그 덮어쓰기는 이전 이미지 자동 삭제가 아니므로, 사용 중인 digest를 삭제하지 않는
수명 주기 정책을 별도로 검토하세요.

운영 집계 뷰의 130번 마이그레이션은 이미지에 포함된 db/와 파이프라인 SQL에 반영됩니다.
이미 사용 중인 Lambda에는 새 이미지를 배포해야 하며 이미지 업로드만으로 DB가 바뀌지는 않습니다.
새 이미지의 실제 initialize/incremental/correction 파이프라인 실행에서 뷰·권한이 적용됩니다.
health·check와 ALREADY_PROCESSED 반환은 이 스키마 적용을 실행하지 않습니다.
기존 데이터가 있는 DB에는 스키마 적용 목적으로 initialize를 실행하지 않고,
관리자 psql에서 [130 스키마 파일](../../db/schema/130_install_operations_monthly_preagg_view.sql)을
[DB 적용 안내](../../db/README.md#운영-고객월-선집계-뷰-적용)에 따라 트랜잭션에서 적용합니다.

## 2. AWS Console에서 Lambda 생성

1. ECR과 같은 리전에서 Lambda → 함수 → 함수 생성.
2. **컨테이너 이미지** 선택. 함수 이름 `kt-nd-pipeline`.
3. 이미지 찾아보기 → 프라이빗 ECR 저장소 → `latest` 선택.
4. 아키텍처 **x86_64**. 기존 Lambda 실행 역할을 선택합니다.
   GitHub ECR 업로드 역할을 Lambda 실행 역할로 쓰면 안 됩니다.
5. 생성 후 구성 → 일반 구성 → 편집:
   메모리 **2048 MB**, 제한 시간 **15분**, 임시 스토리지 **2048 MB**로 시작합니다.
6. 구성 → 동시성에서 **예약된 동시성 1**로 제한합니다. 계정 동시성 한도로 1을
   설정할 수 없다면 할당량을 확인하고, 자동 트리거 없이 수동 실행만 하세요.

2048 MB는 시작 설정이지 처리 시간 보장은 아닙니다. 1일 배치부터 시간을 측정하고
15분을 넘기면 날짜 수를 늘리지 말고 실행 환경·쿼리 성능을 다시 검토하세요.

## 3. 네트워크와 권한

Lambda 구성 → VPC에서 RDS와 같은 VPC의 적절한 서브넷과 Lambda용 SG를 선택합니다.
RDS SG의 TCP 5432 소스는 Lambda SG로 허용합니다. 내 PC IP 허용 규칙은 별개입니다.
공개 서브넷에 Lambda를 넣는 것만으로 인터넷 접근이 생기지는 않습니다.

VPC 안의 Lambda에서 S3와 Secrets Manager에 접근할 경로도 필요합니다.
기존 NAT 경로를 사용하거나 S3 Gateway endpoint와 Secrets Manager Interface endpoint를
구성할 수 있습니다. 후자의 private DNS와 endpoint SG TCP 443 허용을 확인하세요.
NAT Gateway 및 Interface endpoint는 별도 비용이 발생합니다. 기존 구성을 확인한 후 선택하고,
ECR을 위한 NAT를 무조건 만들지 마세요. 이미지 회수는 Lambda 서비스가 담당합니다.

실행 역할에는 로그, VPC ENI, S3의 해당 prefix에 대한 ListBucket/GetObject,
두 Secret의 GetSecretValue 권한이 필요합니다. 고객 관리 KMS 키를 쓰면 해당 키의
Decrypt 권한도 확인합니다. 별도 ECR 이미지 회수 정책은 Lambda 생성 시 확인합니다.

## 4. Lambda 환경 변수

[배포 모듈의 설정 표](../../deploy/README.md#lambda-설정)를 기준으로 Lambda 구성 → 환경 변수에 값을 등록합니다. 연결 비밀번호와 HMAC 키는 Secrets Manager에서 관리합니다.

## 5. 테스트 이벤트: 아래 순서대로 수동 실행

Lambda → 테스트 → 새 이벤트 생성. 이벤트 이름을 정하고 JSON을 입력한 뒤 테스트합니다.
현재 실행 경로는 수동 이벤트입니다. **S3 트리거를 추가하지 않습니다**. 이벤트에는 비밀번호·키를 넣지 않습니다.

### health: 설치와 실행 환경만 확인

```json
{"action": "health"}
```

결과 `status=SUCCEEDED`, `psql`에 18.x, `powershell`에 7.6.6,
`database_accessed=false`, `aws_apis_accessed=false`를 확인합니다.

### check: 연결·권한을 읽기 전용으로 확인

```json
{"action": "check"}
```

Secrets Manager 조회, SSL verify-full RDS 연결, 기준 CSV 13개 존재를 확인합니다.
결과 `database_connected=true`, `master_files_found=13`, `database_modified=false`.
초기 DB에서는 watermark가 null입니다. 스키마 생성이나 적재는 하지 않습니다.

### initialize: 빈 파이프라인 DB에 기준 CSV 적재

```json
{"action": "initialize", "confirm_initialize": true}
```

`initialize_incremental_pipeline.ps1` → `015_initialize_incremental_pipeline.psql`.
진입점에서 스키마를 생성하므로 별도의 DDL 선행 실행은 필요하지 않습니다.
13개 기준 CSV만 다운로드합니다. 사용량 날짜 CSV는 아직 적재하지 않습니다.

기존 초기화 SQL은 DW/DM 데이터를 truncate하므로 Handler는 해당 테이블에 데이터가 있으면
초기화를 거절합니다. 기준 데이터 수정·스키마 변경·재적재 용도로 initialize를 사용하지 마세요.
초기화 중에는 이 Lambda 밖의 다른 적재 프로그램도 실행하지 마세요. 같은 Secret 키를 유지합니다.

### incremental: 최초 1일만 적재

```json
{"action": "incremental", "from_date": "2025-10-24", "to_date": "2025-10-24"}
```

`run_incremental_pipeline.ps1` → `020_run_incremental_pipeline.psql`.
해당 날짜의 직접 `part-*.csv`만 다운로드합니다. 성공 결과의 batch_id와 audit 상태를 확인합니다.
성공 후 다음 from_date는 watermark+1입니다. 처음에는 다음 날짜도 1일로 실행하세요.
충분히 빠른 것을 확인한 뒤에만 최대 7일까지 늘립니다. 하루라도 15분을 넘기면 중단하고 원인을 확인합니다.

전 범위가 이미 워터마크에 포함되면 `ALREADY_PROCESSED`로 종료합니다. 이 응답은 기존 CSV
체크섬을 다시 검증했다는 뜻이 아닙니다. 이전 날짜 데이터가 달라졌다면 correction을 사용합니다.
범위가 기존/신규 날짜에 걸치거나 날짜 간격이 생기면 거절합니다.
한국 시간 오늘·미래 날짜는 차단하며, ProcessingDate는 처리 종료일+1로 설정하여 기존
스크립트가 요청 범위 밖의 파티션까지 요구하지 않게 합니다. 배치 reference_date 역시 이 날짜입니다.

### correction: 이미 적재한 1일의 새 원본 버전 반영

원본 정정 CSV를 사용자가 S3의 다음 경로에 올린 뒤 실행합니다.

```text
kt-nd/raw/content_usage/event_date=2025-10-24/run_id=fix-001/part-000.csv
```

```json
{"action": "correction", "correction_date": "2025-10-24", "correction_version": "fix-001"}
```

이미 성공한 날짜만 허용합니다. 지정한 run_id만 다운로드하여 해당 날짜를 교체하고 기존 SQL이
영향 월을 재집계합니다. 이는 데이터 정정이지 스키마 마이그레이션이 아닙니다.
마이그레이션은 [DB 안내](../../db/README.md#타입과-마이그레이션에서-주의할-점)의 새 번호 SQL·재실행 가능 규칙에 따라 별도로 적용합니다.

## 6. 실행 결과 확인

Lambda 호출이 종료되면 [도구 안내](../../tools/README.md#적재-후-검증)의 검증 SQL을 실행합니다. 요청 배치의 SUCCEEDED 상태, 품질 검사 기록과 실패 행 0개, 증분 워터마크 도달 여부를 함께 확인합니다. 품질 실패 시 검사 기록도 롤백될 수 있어 실패 행이 없다는 사실만으로 성공으로 판단하지 않습니다.

Lambda 모니터링 → CloudWatch Logs 보기에서 단계·action·batch_id를 확인합니다.
보안을 위해 subprocess 원문 출력은 로깅하지 않습니다. 실패 시 먼저 `stage`와 오류 유형을
확인하고, DB 감사 이력은 본인 psql 세션에서 확인하세요. 인증 정보나 원본 행을 로그에 추가하지 마세요.
PGPASSWORD와 HMAC 키는 subprocess 환경으로 전달되고 파일·응답에 저장하지 않습니다.

## 재배포와 실행 한계

ECR `latest`가 바뀌어도 기존 Lambda가 자동으로 새 이미지를 쓰지는 않습니다.
Lambda 코드/이미지 화면에서 **새 이미지 배포(Deploy new image)**를 선택하여 새 digest를 적용합니다.
실제 데이터 품질·네트워크·시간 검증은 Console 실행 후에만 완료됩니다.
수백 날짜를 한 번의 Lambda 호출로 처리하지 않습니다. 초기 적재를 마친 뒤 일별 자동화는
워터마크 순서와 동시 실행을 고려하여 별도로 설계합니다.

참고: [Lambda Python 이미지](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html),
[S3 다운로드 SDK](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/download_file.html),
[Secret 조회 SDK](https://docs.aws.amazon.com/boto3/latest/reference/services/secretsmanager/client/get_secret_value.html),
[Lambda VPC 인터넷 연결](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html).
