# Temporary staging

CSV는 영구 Landing에 저장하지 않습니다. [`001_create_staging.sql`](001_create_staging.sql)이
14개 `pg_temp.stg_*` 테이블을 만들고, 전체 배치 또는 초기화 스크립트가 `\copy`로 채웁니다.
staging은 배치 트랜잭션이 끝나면 자동 삭제됩니다.

`age_benefits.csv`의 빈 `max_age`는 나이 상한이 없다는 뜻입니다(예: 75세 이상).
staging과 두 DW는 이를 NULL로 보존합니다. `min_age`는 필수이며, 상한이 있으면
`max_age >= min_age`여야 합니다. staging 범위 검사와 두 DW의 NULL-safe 비교로 검증합니다.

`premium_family_discount_rules.csv`의 `enrollment_min_age`, `enrollment_max_age`,
`benefit_end_age`는 `0.0`, `18.0`, `20.0`처럼 소수 표기된 정수를 포함합니다. staging은
세 컬럼을 정밀도·소수 자릿수 제한 없는 `numeric`으로 읽어 COPY 단계의 integer 구문 오류를
피하고, 입력을 먼저 반올림하지 않습니다. 빈 값은 NULL로 유지합니다.
`staging_premium_family_age_integer` 품질 검사는 NULL 또는 integer 범위
(-2147483648~2147483647)의 정확한 정수만 허용합니다. 실제 소수 값(예: `18.5`),
범위 초과, NaN·무한대는 거절합니다. 검사 후 공통 마스터 적재 SQL이 세 컬럼을
명시적으로 `::integer` 변환하여 두 DW에 저장합니다.

생성기·CSV·S3 객체·감사 체크섬은 변경하지 않습니다. 영구 DW 타입도 integer 그대로이며
임시 staging만 바꾸므로 별도의 DB 마이그레이션은 필요하지 않습니다. 실패한 초기 적재는
새 Lambda 이미지를 배포한 뒤 동일한 이벤트로 재시도합니다. 실제 DB 검증은 요청 배치의
`audit.pipeline_run.status='SUCCEEDED'`와 품질 결과의 실패 행 0개를 함께 확인합니다.

PowerShell 실행기는 CSV 폴더의 절대 경로를 psql 변수 `input_csv_directory`로 전달합니다.
적재 SQL은 `\cd :input_csv_directory`로 클라이언트 작업 폴더를 지정한 뒤 고정 CSV 파일명을
`\copy`에 사용합니다. `\copy` 자체는 psql 변수를 치환하지 않습니다. 감사용 원본 경로·체크섬
변수와 `\ir`의 SQL 파일 기준 상대 경로는 그대로 유지합니다.

| 파일 | 역할 |
| --- | --- |
| `001_create_staging.sql` | 14개 임시 테이블 DDL |
| `005_load_master_staging.psql` | 사용량을 제외한 13개 CSV staging 및 감사 메타데이터 |
| `010_load_full_staging.psql` | 14개 전체 CSV staging |
| `020_load_incremental_content_usage.psql` | 날짜 파티션 사용량과 manifest staging |

S3가 원본의 단일 기준점입니다. AWS 실행 환경에서는 S3 객체를 작업 디렉터리로 내려받은 뒤
동일한 psql 스크립트를 실행합니다. 운영 Lambda가 처리하는 원본 ID는 staging 밖으로
저장하지 않고 운영 DW 적재 시 즉시 HMAC 키로 치환합니다.
