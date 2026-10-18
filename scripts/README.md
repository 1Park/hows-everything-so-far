# 실행·진단

레포 루트/venv에서 실행한다. [전체 설치](../README.md).

| 도구 | 역할 |
| --- | --- |
| dev.py | direct/fixture/offline/proxy/integration/board 모드, 포트·lock 검사, startup 실패 시 자식 정리, 로그 |
| dev.py --stop | matching mode/port supervisor 종료 완료까지 대기 후 반환; --mode board에는 동일 옵션 사용 |
| start-board.sh / stop-board.sh | Linux native background supervisor, PID·중복 검사·실패/종료 대기 |
| diagnose.py | OS/arch/Python, 명시 runner/model/library, camera/Bridge/router read-only 진단 |
| runner_smoke.py -- <실제 runner와 flags> | 단일 입력 실행·시간/출력/오류 logs 기록; CLI를 추측하지 않음 |
| smoke.py | 실제 Controller HTTP를 통해 리필/수정/stale/duplicate/완료/STT/skip 검증 |
| browser_auto_capture.cjs | 로컬 앱에서 3초 자동 시작·모드 전환·snapshot/bbox·모바일 화면 검사 (fixture 검증) |
| evaluate_qwen.py --proxy | 실제 local proxy→Mac 음료 평가, temperature0, timestamp 신규 결과 |
| evaluate_gemma.py | 보드 HTTP Gemma 평가: 원본20 + 합성 STT 왜곡20, 동일 제품 프롬프트, 케이스별 input/output/시간을 신규 JSON·Markdown에 기록 |
| build_vision_worker.py | 주최 측 SDK를 수정하지 않고 별도 출력 경로에서 DINO/YOLO 상주 native worker 빌드 |
| benchmark_vision_residency.py | 같은 이미지·bundle로 CLI/상주 invoke 시간·초기 로드·출력 동등성 비교, 신규 JSON/Markdown 기록 |
| browser_check.cjs | 실제 Chromium 녹음/fixtureSTT/고정 오디오/카드/확인/취소/반응형/재연결 |
| browser_board_voice.cjs | 자동 인식→태블릿 안내 재생 완료→보드 fixture 녹음→STT→카드, 브라우저 마이크 미사용 |

logs/서비스명.log, tmp/lock은 Git 제외. Ctrl+C 또는 --stop. 외부 Mac 서버·호스트 arduino-router·MCU firmware·Tailscale Serve는 이 supervisor가 시작/종료하지 않는다. board --stop은 shell stop 도구와 같은 managed supervisor만 대상으로 한다.

fixture는 Vision/STT/Hardware만 고정하고 Qwen은 QWEN_BASE_URL의 실제 HTTP API(기본 Mac)를 사용한다. offline은 Qwen도 fixture로 고정하며 외부 모델 연결 없이 실행한다. 이 두 모드는 Controller/UI만 시작한다. 실제 API 장애를 fixture로 자동 전환하지 않는다.

`--mode direct --with-stt`는 Controller와 우리 STT API만 관리하며 Qwen은 설정된 원격 API를 유지한다. 기존 whisper-server는 별도 프로세스로 유지하고 종료하지 않는다. 보드 마이크 설정은 [태블릿 시연](../docs/TABLET_DEMO.md)을 참고한다.
