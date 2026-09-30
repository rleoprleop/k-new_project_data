# Temporary staging

CSV는 영구 Landing에 저장하지 않습니다. [`001_create_staging.sql`](001_create_staging.sql)이
14개 `pg_temp.stg_*` 테이블을 만들고, 전체 배치 또는 초기화 스크립트가 `\copy`로 채웁니다.
staging은 배치 트랜잭션이 끝나면 자동 삭제됩니다.

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
