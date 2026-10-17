# 실제 Demo UI

Controller가 `/`에서 제공하는 프레임워크 없는 HTML/CSS/JS. 설명용 docs/architecture.html과 별개다. 태블릿 우선 **브라우저 마이크/스피커**: MediaRecorder→STT 전송→전사 검토→Send, Web Audio 고정 WAV. 서버 오디오 장치/live TTS 없음.

분석 이미지·bbox·컵ID/잔량·frozen target card·Confirm/Cancel·WS 재연결·fixture/source 표시. 카메라는 Controller만 열고 UI는 영상만 받는다. [HTTPS 접속](../../docs/TABLET_DEMO.md). audio/*.wav는 개발 시 Windows SAPI로 생성한 고정 영어 안내이며 입력 기반 TTS 생성은 하지 않는다. 텍스트/파일 입력도 제공한다.
