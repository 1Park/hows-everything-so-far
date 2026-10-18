# 브라우저 UI

Controller가 `/`에서 HTML/CSS/JS를 제공한다. `/dashboard`는 mock·live 이벤트 이력, `/stt`는 전사 정확도 측정 도구다.

보드가 카메라·마이크를, 브라우저가 UI·스피커를 소유한다. TTS 안내 종료 후 ACK → 보드 녹음 → STT → LLM → 카드로 진행한다. 최초 Enable sound가 필요하다. `TTS_BACKEND=http`에서는 환영·Replay voice도 TTS를 사용하고, 실패 시 오류를 표시하며 예전 WAV로 대체하지 않는다. 개발용 `TTS_BACKEND=disabled`에서만 고정 WAV를 사용한다. `AUDIO_INPUT=disabled`에서는 개발용 브라우저 녹음·전사 검토·Send를 제공한다.

상태는 WS로 받고 instance_id/sequence로 늦은 응답을 무시한다. 분석 snapshot과 bbox를 함께 표시하며 live preview와 구분한다. 캡처 모드와 안정성 진행도는 별도 capture 이벤트로 갱신한다. Confirm은 현재 카드에서만 가능하다.

Controller `/health`를 1초 간격, 요청당 2초 제한으로 확인한다. 접속이 끊기면
`bad cable connection` 안내를 표시하고 입력과 녹음을 막는다. 연결이 돌아오면
새 WebSocket의 최신 상태를 받은 뒤 안내를 닫고 영상도 재연결한다. 페이지를
새로고침하거나 이전 요청을 자동 재전송하지 않는다. 케이블, 네트워크, 서버 중단은
브라우저에서 구분할 수 없으므로 같은 안내를 사용한다.

재연결 검증: 별도 offline 서버를 8096 포트에서 실행한 뒤 `npm run test:reconnect`.

Demo tools의 **Enable untrained drink variants (demo only)** 는 기본 OFF다.
ON이면 water 관찰에서 water/sparkling water/soda, coke 관찰에서 coke/coke zero/coffee를
선택할 수 있다. 추가 종류를 이미지에서 식별했다는 뜻은 아니며 고객 발화와 LLM이 선택한다.
서버 재시작 시 OFF, 페이지 새로고침 시에는 현재 서버 설정을 유지한다.
옵션 변경은 기존 카드를 폐기한다. 고정 분류 매핑 자체는 읽기 전용이다.
검증: offline 서버에서 `node scripts/browser_categories.cjs` (기본 포트 8088).

[캡처 모드](../../docs/AUTO_CAPTURE.md), [태블릿 사용](../../docs/TABLET_DEMO.md), [브라우저 검증](../../docs/VALIDATION.md).
