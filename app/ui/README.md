# 브라우저 UI

Controller가 `/`에서 HTML/CSS/JS를 제공한다. `/dashboard`는 mock·live 이벤트 이력, `/stt`는 전사 정확도 측정 도구다.

보드가 카메라·마이크를, 브라우저가 UI·스피커를 소유한다. 고정 WAV 안내 종료 후 ACK → 보드 녹음 → STT → LLM → 카드로 진행한다. 최초 Enable sound가 필요하며 live TTS는 없다. `AUDIO_INPUT=disabled`에서는 개발용 브라우저 녹음·전사 검토·Send를 제공한다.

상태는 WS로 받고 instance_id/sequence로 늦은 응답을 무시한다. 분석 snapshot과 bbox를 함께 표시하며 live preview와 구분한다. 캡처 모드와 안정성 진행도는 별도 capture 이벤트로 갱신한다. Confirm은 현재 카드에서만 가능하다.

[캡처 모드](../../docs/AUTO_CAPTURE.md), [태블릿 사용](../../docs/TABLET_DEMO.md), [브라우저 검증](../../docs/VALIDATION.md).
