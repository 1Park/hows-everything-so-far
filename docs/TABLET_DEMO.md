# 태블릿 마이크·스피커 시연

**보드 Controller가 마이크 녹음, 태블릿 브라우저가 UI·스피커를 담당한다.** STT 서버는 파일 입력만 받으며 마이크를 다시 열지 않는다. 앱은 모델 전처리/resampling을 하지 않는다. 고정 WAV 안내를 Web Audio로 재생하며 실제 TTS는 없다.

## 접속

보드 마이크 흐름에는 HTTPS가 필요 없다. 현재 이더넷 설정은 end0 `192.168.50.1/24`, NetworkManager `refill-tablet` DHCP 자동 배정이다. 태블릿 이더넷을 자동 IP/DHCP로 두고 **http://192.168.50.1:8080/** 을 연다. UI 접속은 인터넷·Tailscale 없이 가능하다. Mac Qwen 호출은 보드→Mac 연결이 별도로 필요하다.

HTTPS를 원하는 경우에만:

```sh
python scripts/dev.py --mode integration
tailscale serve --bg --https=443 http://127.0.0.1:8080
tailscale serve status
```

태블릿도 같은 tailnet에 연결하고 출력된 HTTPS URL을 연다. tailnet HTTPS 활성화/권한이 필요할 수 있다. 기존 Serve 설정은 먼저 status로 확인한다. 이더넷 HTTP 직접 접속에는 CONTROLLER_HOST=0.0.0.0을 설정한다.

`AUDIO_INPUT=disabled`일 때만 개발용 브라우저 녹음 경로를 제공한다. 이 경로에만 getUserMedia의 HTTPS/localhost 조건이 적용된다. [MDN 마이크 요건](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia), [Tailscale Serve HTTPS](https://tailscale.com/docs/reference/tailscale-cli/serve).

## 시연

1. 태블릿에서 Enable sound를 한 번 눌러 스피커 재생을 활성화한다. 새로고침 후에는 다시 필요하다.
2. `OBSERVE_INTERVAL_SECONDS=5`이면 idle/skip 중 5초마다 관찰한다. 외부 호출자의 `POST /api/observe` multipart 이미지도 트리거가 된다. Start demo는 수동 진단용이다.
3. offered WS 이벤트로 대상 이미지·bbox·질문이 갱신되고 태블릿 안내를 재생한다.
4. 안내가 **끝난 뒤** session/scene/object/sequence ACK를 보낸다. 음소거·재생 실패·취소·장면 변경이면 자동 녹음하지 않는다.
5. 보드 마이크가 설정된 시간(기본6초, 최대15초) WAV 녹음→STT→Qwen을 실행한다. UI: LISTENING→TRANSCRIBING→INTERPRETING→CARD. 자동 무음 감지/VAD는 구현하지 않았다.
6. 전사/source와 카드를 표시한다. 고객 Confirm 전에는 동작하지 않는다. Cancel은 녹음을 중단하고 늦은 결과를 무시한다.
7. 완료/거절/취소/만료 후에는 반복 질문하지 않는다. 다음 테이블은 외부 관찰 트리거나 Inspect again으로 시작한다. 연결이 끊기면 입력을 막고 재연결 후 최신 상태를 복구한다.

[브라우저 autoplay 정책](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay)에 따라 최초 Start demo/Enable sound 사용자 동작이 필요하다. 외부 스피커는 태블릿 블루투스/유선 출력에 연결한다. 마이크는 보드 USB/ALSA 장치를 사용한다.

## 현재 보드의 기존 Whisper 서버 연결 예시

확인된 USB 입력은 `hw:CARD=B101,DEV=0` (Brio 101), S16_LE/mono/16–48kHz다. 장치가 달라지면 `arecord -l`과 지원 형식을 다시 확인한다. 기존 whisper.cpp 서버 127.0.0.1:8178의 모델/설정은 변경하지 않는다.

```bash
export CONTROLLER_HOST=0.0.0.0
export QWEN_BASE_URL=http://won-macmini:8000
export VISION_BACKEND=fixture  # 실제 Vision 연결 시 담당자 설정 사용
export HARDWARE_BACKEND=mock
export AUDIO_INPUT=alsa
export AUDIO_DEVICE=hw:CARD=B101,DEV=0
export AUDIO_FORMAT=S16_LE
export AUDIO_RATE=16000
export AUDIO_CHANNELS=1
export AUDIO_SECONDS=6
export OBSERVE_INTERVAL_SECONDS=5
export STT_MODEL_BACKEND=external
export STT_ADAPTER=services.stt.whisper_http:create_backend
export STT_WHISPER_URL=http://127.0.0.1:8178
.venv/bin/python scripts/dev.py --mode direct --with-stt --env-file .env.board
```

Controller+우리 STT API만 시작한다. Mac Qwen과 기존 whisper-server는 외부 프로세스다. Ctrl+C 또는 같은 모드/포트의 --stop으로 앱만 종료한다. `--mode fixture`는 STT까지 고정 결과로 강제하므로 실제 Whisper 검증에는 쓰지 않는다.

## 보드 없는 자동 흐름 검증

```bash
AUDIO_INPUT=fixture OBSERVE_INTERVAL_SECONDS=0.5 CONTROLLER_PORT=8090 \
  python scripts/dev.py --mode offline
REFILL_URL=http://127.0.0.1:8090 npm run test:board-voice
```

fixture capture는 무음 WAV, fixture STT는 고정 영어 문장이다. 브라우저가 마이크를 열지 않는 것과 안내 완료→녹음→카드를 검사하며 실제 장치·인식 정확도를 대신하지 않는다. 보드 실제 녹음·STT 정확도·태블릿 청취·장치 점유는 현장 검증 대상이다.
