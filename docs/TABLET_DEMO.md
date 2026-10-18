# 태블릿·음성 흐름

Controller가 보드 카메라·마이크를 소유하고 태블릿 브라우저가 UI·스피커를 소유한다. STT 서비스는 파일 입력만 받는다. `TTS_BACKEND=http`에서는 안내·환영·Replay voice 모두 보드 TTS를 사용한다. 실패 시 이전 WAV로 대체하지 않고 오류를 표시한다. 개발에서 TTS를 명시적으로 disabled로 설정할 때만 고정 WAV를 사용한다.

## 접속·사용

1. [보드 runbook](BOARD_RUNBOOK.md)으로 서비스를 실행하고 태블릿에서 `http://<board-address>:8080/`을 연다. 외부 접속에는 `CONTROLLER_HOST=0.0.0.0`이 필요하다.
2. Enable sound로 스피커를 활성화한다. 새로고침하면 다시 필요할 수 있다.
3. Start demo 또는 [Automatic 캡처](AUTO_CAPTURE.md)로 관찰한다. 자동 모드는 기본 3초간 객체 종류별 개수가 같아야 시작하며 동일 구성은 반복 안내하지 않는다.
4. 대상 제안 안내가 끝나면 브라우저가 현재 session/scene/object/sequence로 ACK한다. 음소거·재생 실패·취소된 안내는 녹음을 시작하지 않는다.
5. 보드가 설정 시간 동안 녹음 → STT → LLM → 카드까지 진행한다. UI는 LISTENING → TRANSCRIBING → INTERPRETING → CARD로 바뀐다. VAD는 없으며 녹음 길이는 `AUDIO_SECONDS`다.
6. 전사·음료를 확인하고 수정·Confirm 또는 Cancel한다. LLM `not_understood`와 STT `no_speech`·timeout은 재질문 상태로 전환하고, 안내 재생이 끝나면 현재 상태 ACK 후 자동으로 보드 녹음을 다시 시작한다. 취소·장면 변경·음소거·재생 실패 시 자동 녹음하지 않는다. 기타 서비스 장애는 error 상태에서 수동 재시도한다. 카드만으로 하드웨어를 시작하지 않는다.

네트워크 단절 시 입력을 막고 재연결 후 최신 상태를 복구한다. 자동 캡처 재시작은 안정성 구간을 다시 시작한다. 수동 시작·모드 전환·동일 테이블 재시작 규칙은 자동 캡처 문서를 따른다.

## 오디오 설정

`.env.board`는 `AUDIO_INPUT=alsa`, B101 장치, S16_LE/16kHz/mono/4초를 사용한다. 장치 교체 시 `arecord -l`과 지원 형식을 확인해 `AUDIO_DEVICE/FORMAT/RATE/CHANNELS/SECONDS`를 설정한다. 보드 녹음에는 태블릿 마이크 권한·HTTPS가 필요 없다.

`AUDIO_INPUT=disabled`일 때는 개발용 브라우저 녹음·전사 검토·Send를 제공한다. 브라우저 마이크 사용은 HTTPS 또는 localhost에서 실행한다. `AUDIO_INPUT=fixture`는 테스트용 무음 WAV를 생성한다.

보드 없는 안내 종료→녹음→카드 검증은 [검증 명령](VALIDATION.md)을 따른다. fixture·가상 마이크 결과는 실물 마이크 정확도나 스피커 청취 검증이 아니다.
