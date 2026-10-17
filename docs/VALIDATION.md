# 보드 전 구현·검증 결과

검증일: 2026-10-16 (Pacific), 결과 파일명은 UTC2026-10-17. Windows11 AMD64/Python3.13, Chrome 실제 브라우저, Tailscale→Mac MLX. 보드 없음.

## 구현·실행 결과

- Controller 상태/리필 정책/영어 제품 프롬프트/엄격 파서/수정/취소/무응답/재시도/명시 확인, 상태 mock HardwareIO 구현.
- Qwen 독립 FastAPI: MLX HTTP·명시 fixture·미연결 ExecuTorch 경계, 생성 옵션/입력 검증·bounded queue·timeout·health/readiness.
- Vision/STT: API·schema·입력 제한·fixture·external async factory/HTTP·오류/readiness. 검출/crop/DINO/STT 모델·전후처리는 구현하지 않았음.
- 실제 앱 UI: 태블릿 브라우저 녹음·원본 전달·전사 검토·고정 WAV 재생, frozen frame/bbox/대상 카드·Confirm/Cancel·연결 복구·반응형. live camera/video source는 별도 live ribbon으로 계속 표시.
- direct/fixture/proxy/integration 모드, 프로세스별 logs·포트/lock·시작 실패 rollback·graceful stop/재시작. board shell·진단·runner smoke 준비.

## 자동 테스트·통합

`python -m pytest -q`: **45개 통과**. 정상/음료·분량 수정/거절/취소/모호/충분/저신뢰·엄격 JSON/중복키/허용값·오래된/중복/대상 불일치 확인·취소 뒤 late inference·확인/취소 경쟁·timeout/재시도·무응답 expiry·raw body/media 제한·상태/WS·외부 adapter 오류/timeout/readiness·실제 MLX HTTP 오류(no fallback)·영상 파일 EOF loop·supervisor start/중복/stop/restart/실패 rollback. Bridge 검증은 가짜 official-module transport 계약만이며 실기가 아님.

`python -m ruff check app common services scripts tests`, compileall, pip check 통과. shell start/stop은 Git Bash `bash -n` 구문 검사; 실제 Ubuntu/보드 daemon 실행은 미검증. Starlette TestClient의 httpx deprecation warning이 있지만 테스트 실패가 아니다.

45개 테스트 검증 환경에는 선택 camera extra가 설치되어 있다. 기본 dev만 설치하면 영상 파일 loop 테스트1개는 명시 skip하고 나머지를 실행한다.

별도 빈 venv(tmp/fresh-install)를 만들고 README의 requirements.lock 제약으로 editable/dev 설치와 pip check를 완료했다. 그 환경에서도 integration 서버·실제 Mac 경유 전체 smoke를 재현했다.

`python scripts/dev.py --mode integration` + `python scripts/smoke.py`로 **Controller→우리 Qwen API→실제 Mac MLX** 경로 확인. 모델 목록 API에 `mlx-community/Qwen3-0.6B-4bit` 존재. 리필(water/small)→coffee/regular 수정→오래된 확인409→Confirm→중복409→mock done, STT fixture 전달, enough/uncertain skip 통과. 종료 후 같은 integration 모드 재시작·동일 smoke 재현. 서버 모델/설정은 변경하지 않았다.

`npm run test:browser`는 실제 Chromium에서 가상 마이크로 녹음→STT fixture 전달→전사 검토→Send→Mac Qwen 카드→수정→Confirm→done, decline/cancel, 연결 offline/reconnect를 확인. MJPEG preview와 이미지 upload도 검사한다. 스크린샷1440/820/768/390px, bbox 정규화 위치/이미지 비율·가로 overflow 없음. 고정 WAV decode 성공·AudioContext running/재생·Sound on 유지 확인. 스크린샷/기계 결과는 Git 제외 tmp/browser-qa에 생성되며 재실행 가능하다. **가상 마이크이므로 실제 STT 정확도/물리 스피커 청취 검증은 아니다.**

빠른 fixture의 WS 이벤트가 이전 REST 응답보다 먼저 도착하는 경쟁을 재현해 instance_id/sequence로 역전 갱신을 차단했다. 브라우저 검증에서 첫 관찰 HTTP 응답을 일부러 지연해 회귀 검사한다. multipart 파일은 이 지연 장치가 원본을 손실하지 않도록 실제 브라우저 경로로 직접 전송한다.

CAMERA_SOURCE에 샘플 AVI 파일을 지정한 실제 서버에서도 전체 fixture 브라우저 검증을 재실행해 반복 영상·항상 보이는 live ribbon·고정 분석 bbox·이미지 업로드와 녹음 흐름을 확인했다. 설명 HTML도 모든7단계·개발/보드 토글·1440/820/390px에서 이미지 로딩·overflow·JavaScript 오류를 검사했다.

## 실제 Qwen 평가

20개 영어 음료 사례, temperature=0, thinking=false 요청, max_completion_tokens192, stream=false. expected intent/item/portion 모두 일치해야 정답. 단일 JSON Markdown fence는 제거하지만 필드를 보정하지 않는다. fixture fallback 없음. 프롬프트 보완에 사용한 개발 평가셋이므로 held-out 일반화 성능으로 해석하지 않는다.

| 신규 결과 | 의미 |
| --- | --- |
| [060535](qwen_evaluation/drinks-20261017T060535441028Z.json) | proxy 생성옵션 계약 불일치로 요청422. 실제 생성 실패 기록이며 모델 정확도0%로 해석하지 않음 |
| [060722](qwen_evaluation/drinks-20261017T060722867674Z.json) | 첫 실제 평가15/20, 프롬프트 보완 전 |
| [061614](qwen_evaluation/drinks-20261017T061614204547Z.json) | 최종 제품 프롬프트17/20(85%), HTTP 왕복 중앙값0.679초 |

최종 실패3개: `Coke instead, please`에서 regular를 small로 해석; `I'm fine`은 decline 대신 clarify; `Actually a regular coffee`는 refill 대신 clarify. 출력은 허용 schema였으나 의미가 틀렸다. 결과를 정답으로 바꾸지 않고 원본 raw를 보존했다. 메뉴/schema 검증만으로 의미 정확도를 보장할 수 없으므로 사용자가 카드에서 수정/취소하고 최종 Confirm한다. 기존 .py.md/.json.md 평가 아카이브는 변경하지 않았다.

위 시간은 Windows→우리 proxy→Mac HTTP 전체 응답이며 보드 inference/NPU/TTFT/token throughput/실제 STT 성능과 무관하다. 서버 옵션 적용·가중치 checksum을 독립 감사한 결과는 아니다.

## 외부 의존성과 남은 작업

| 항목 | 현재 상태 / 실제 필요한 것 |
| --- | --- |
| Vision 모델 | 팀원 소유. API·fixture/external 연결은 완성. 실제 detector/crop/DINO·라벨/bbox를 팀원이 연결하고 정확도 확인 |
| STT 모델 | 팀원 소유. 원본 오디오 전달은 확인. WebM/Opus·Safari MP4/AAC 지원/실제 영어 인식 확인 필요 |
| ExecuTorch/QNN | 보드/runner/bundle/SDK 경로 미제공. ExecuTorchBackend는 명시 not-ready503. 경로·상주 실행·토크나이저·취소/성능/NPU delegation은 현장 검증 |
| Bridge/MCU | 공식 RPC API 기반 adapter·nonblocking/cancel/watchdog 초안. 실제 board core compile, LED polarity·package 버전·router·timeout/단절/센서 연결 미검증 |
| 물리 카메라 | 영상 파일 capture·loop·MJPEG 검증. 실제 USB 권한·index·연결 끊김 현장 확인 |
| 물리 태블릿 | Chromium 실제 UI·녹음 transport·WebAudio·태블릿 너비 검증. iPad/Android 권한·실제 mic/speaker·HTTPS tailnet 설정은 현장 장치 필요 |

구체적인 연결 순서는 [보드 runbook](BOARD_RUNBOOK.md), [태블릿 runbook](TABLET_DEMO.md), [담당자 계약](CONTRACTS.md). Tailscale Serve는 기존 tailnet 서비스 설정을 자동 변경하지 않았고 설치·HTTPS 명령을 문서화했다. 앱/테스트 프로세스는 검증 종료 후 모두 정리한다. logs/와 tmp/ QA 산출물만 남기고 Mac 공유 모델 서버는 건드리지 않는다.
