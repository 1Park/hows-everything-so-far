# 실제 Demo UI

Controller가 `/`에서 제공하는 프레임워크 없는 HTML/CSS/JS. 설명용 docs/architecture.html과 별개다. 태블릿 우선 **브라우저 마이크/스피커**: MediaRecorder→STT 전송→전사 검토→Send, Web Audio 고정 WAV. 서버 오디오 장치/live TTS 없음.

새 장면은 이전 입력·전사·녹음을 초기화한다. 취소된 녹음과 늦게 승인된 마이크 권한은 폐기하며, 늦은 STT 결과는 사용자가 수정한 텍스트를 덮어쓰지 않는다. 요청 전송 중 중복 제출을 차단하되 취소는 가능하다. 취소·거절·만료 후 요청 카드는 숨긴다. 분석 프레임이 로드되기 전에는 bbox를 숨긴다.

`--mode offline` 서버에서 `npm run test:browser`와 `npm run test:ui-regressions`로 브라우저 동작을 검증한다. `REFILL_URL`, `CHROME_PATH`로 주소와 설치된 Chrome 경로를 지정할 수 있다. 테스트의 마이크는 가상 장치이며 실물 태블릿·마이크 검증을 대신하지 않는다.

분석 이미지·bbox·컵ID/잔량·frozen target card·Confirm/Cancel·WS 재연결·fixture/source 표시. 카메라는 Controller만 열고 UI는 영상만 받는다. [HTTPS 접속](../../docs/TABLET_DEMO.md). audio/*.wav는 개발 시 Windows SAPI로 생성한 고정 영어 안내이며 입력 기반 TTS 생성은 하지 않는다. 텍스트/파일 입력도 제공한다.
