# 태블릿 마이크·스피커 시연

**태블릿 브라우저가 UI·마이크·스피커를 모두 담당**한다. MediaRecorder 원본을 Controller→STT로 전달한다. 녹음 최대15초, 기본10MB. 전사 검토 후 Send→카드→Confirm. 고정 WAV 안내를 Web Audio로 재생하며 실제 TTS 서비스는 없다. WAV는 개발 시 Windows SAPI로 한 번 생성한 고정 파일이다.

## 접속

노트북 또는 보드에서:

```sh
python scripts/dev.py --mode integration
tailscale serve --bg --https=443 http://127.0.0.1:8080
tailscale serve status
```

태블릿도 같은 tailnet에 연결하고 출력된 HTTPS URL을 연다. tailnet HTTPS 활성화/권한이 필요할 수 있다. 앱은 loopback bind를 유지한다. 기존 Serve 설정은 먼저 status로 확인한다. 앱 launcher는 네트워크 설정을 자동 변경하지 않는다.

`http://보드-IP:8080`에서는 화면이 열려도 태블릿 마이크를 쓸 수 없다. getUserMedia에는 secure context가 필요하고 localhost 예외는 태블릿 자신의 localhost만 해당한다. [MDN 마이크 요건](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia), [Tailscale Serve HTTPS](https://tailscale.com/docs/reference/tailscale-cli/serve).

## 시연

1. 태블릿 음량·출력 경로 확인 후 Start demo를 직접 누른다. 여기서 AudioContext를 활성화한다.
2. Record request → 마이크 권한 허용 → 영어 발화 → Stop recording.
3. 전사 source 확인. 기본 fixture는 모든 오디오에 A little water, please를 반환하며 실제 음성 인식이 아니다.
4. 전사 텍스트 검토/수정 → Send → 카드 → Confirm refill. Cancel은 모델과 무관하게 처리한다.
5. 권한 거절/미지원이면 영어 오류 표시. 텍스트/파일 업로드도 가능. STT 담당자는 WebM/Opus와 iPad Safari MP4/AAC 지원 범위를 확인해야 한다. 서버는 resampling하지 않는다.
6. 연결이 끊기면 확인/입력을 막고 WS 재연결 후 최신 상태 복구.

[브라우저 autoplay 정책](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay)에 따라 Start demo/Enable sound 사용자 동작이 필요하다. 외부 스피커도 태블릿 블루투스/유선 출력에 연결한다. 서버 USB 오디오 장치는 필요 없다.

자동 검증은 실제 Chromium+가상 마이크로 녹음/전달·fixture STT·오디오 decode/playback context·태블릿 너비를 검사한다. 물리 태블릿의 권한·실제 청취·STT 정확도는 현장 확인 대상이다. 기존 사용자 네트워크 구성을 바꾸지 않도록 Tailscale Serve는 자동 설정하지 않았다.
