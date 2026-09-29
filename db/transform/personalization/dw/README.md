# Personalization DW

`dw_personalization`은 14개 CSV의 업무 키와 컬럼을 유지합니다. `users`에는 `user_id`와
`name`이 함께 있고, `content_usage`에는 category와 제한적 detail이 모두 있습니다.
현재 요금제만 사용하며 요금제 변경 이력이나 스냅샷은 만들지 않습니다.

접근 동의가 완료된 데이터라는 전제이지만 운영 workflow와 계정을 분리합니다. 운영 역할은
이 스키마에 접근하지 못합니다.
