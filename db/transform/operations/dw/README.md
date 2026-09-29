# Operations DW

`dw_operations`는 14개 CSV와 같은 논리 테이블명을 사용합니다. `fact_` 접두사를 사용하지
않습니다. `users.name`은 만들지 않으며 user/family/bundle/user-service/user-discount ID는
용도별 HMAC-SHA256 키로 치환합니다.

운영 `content_usage` grain은 가명 사용자×일자×category입니다. 원천 detail을 합산한 뒤
저장하므로 운영 영역에서 detail을 복원하거나 조회할 수 없습니다. 현재 요금제와 가입일은
유지하며 가입자는 `subscription_start_date <= 기준일`로 계산합니다.
