# Demo UI

실제 Controller에 연결되는 시연 웹 화면의 HTML·CSS·JavaScript와 고정 안내 음성 파일을 둔다. UI framework는 아직 정하지 않았다. Controller가 UI를 제공하는 구성을 기본으로 한다.

- 라이브 영상 위 bbox·컵 ID·종류·잔량 표시
- 분석 당시 이미지가 고정된 요청 카드
- 영어 안내·고객 텍스트 입력·Confirm / Cancel
- WebSocket 상태 수신, 연결 상태, 브라우저 오디오 재생

영상은 Vision 서비스의 단일 카메라 소유 모듈이 제공한다. UI는 카메라를 별도로 열지 않는다. STT 위치·연결 방식은 미정이다.

`docs/architecture.html`은 오프라인 설명 문서이며 이 실제 시연 UI와 별개다. 예시 이미지·JSON을 실제 측정 결과로 표시하지 않는다.
