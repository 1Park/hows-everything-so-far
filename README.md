# Refill Assist

Arduino VENTUNO Q에서 컵 종류·잔량을 관찰하고 고객의 영어 요청을 해석한다. 고객이 확인 카드를 **Confirm**하면 mock 적재·복귀 시퀀스를 시작한다. 메뉴는 water/coke/coffee이며 실제 주행·집기는 구현하지 않는다.

동작·설정의 기준은 코드다. 문서는 실행 방법과 코드 위치를 안내하며, 평가 기록은 실행 당시의 결과다.

## 로컬 실행

Python 3.11–3.13. 레포 루트에서:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -c requirements.lock -e '.[dev]'
Copy-Item .env.example .env
.venv/Scripts/python.exe scripts/dev.py --mode offline
```

macOS/Linux는 `.venv/bin/python`과 `cp .env.example .env`를 사용한다.
`http://127.0.0.1:8080` → Start demo → 텍스트 요청 → Send → Confirm refill.
종료는 Ctrl+C 또는 같은 설정으로 `python scripts/dev.py --stop`.

| 모드 | 시작하는 서비스 | 모델 연결 |
| --- | --- | --- |
| `direct` (기본) | Controller/UI | 설정된 API/fixture. 기본은 Vision·STT fixture + Mac Qwen HTTP |
| `fixture` | Controller/UI | Vision·STT fixture, Hardware mock, LLM은 실제 HTTP |
| `offline` | Controller/UI | LLM 포함 모두 fixture, Hardware mock |
| `proxy` | Controller + Qwen API | Qwen 서버가 설정된 backend 호출 |
| `integration`, `board` | Controller + Qwen + Vision + STT | 선택 env의 backend 사용 |

`--mode direct --with-stt`는 STT API도 관리한다. 보드에서 별도로 실행 중인 모델 서버가 있으면 [보드 runbook](docs/BOARD_RUNBOOK.md)을 따른다. 모델 장애를 fixture로 자동 대체하지 않는다.

설정 우선순위는 코드의 명시 override > 프로세스 환경변수 > 선택 dotenv(`--env-file`/`REFILL_ENV_FILE`, 기본 `.env`) > [`Settings`](common/config.py) 기본값이다. `.env.board`만으로 실제 Vision이 선택되지는 않으며 bundle 설정도 필요하다.

## 구성

| 코드 | 책임 |
| --- | --- |
| [app/](app/README.md) | 상태 머신·리필 정책·프롬프트·단일 카메라·보드 녹음 |
| [app/ui/](app/ui/README.md) | 태블릿 UI·고정 WAV 안내·확인·대시보드 |
| [services/qwen/](services/qwen/README.md) | 보드 상주 Gemma4 / 개발 Mac HTTP 생성 API |
| [services/vision/](services/vision/README.md) | YOLO → DINOv2 → head, 보드 모델 상주 |
| [services/stt/](services/stt/README.md) | whisper.cpp HTTP 연결·전사 정규화 |
| [app/hardware/](app/hardware/README.md) | mock 또는 arduino-router RPC |
| [common/](common/README.md) | 스키마·설정·오류·추론 queue |
| [ml/](ml/README.md) | 학습·평가·export; 앱 런타임과 별도 |
| [scripts/](scripts/README.md) | supervisor·진단·빌드·평가 도구 |

카메라와 마이크는 Controller, UI·스피커는 브라우저가 소유한다. 선택 영상/USB 입력은 `.[camera]`를 설치하고 `CAMERA_SOURCE`로 지정한다. 빈 값은 명시적 샘플 이미지다.
캡처는 기본 수동이며 UI에서 Automatic으로 바꾸면 3초 안정성 판정 후 시작한다. [자동 캡처](docs/AUTO_CAPTURE.md).

## 문서·검증

- [구조와 실행 경로](docs/ARCHITECTURE.md), [API 경계](docs/CONTRACTS.md)
- [보드 배포·실행](docs/BOARD_RUNBOOK.md), [태블릿·음성 흐름](docs/TABLET_DEMO.md), [모델 파일](models/README.md)
- [검증 명령과 범위](docs/VALIDATION.md)
- 과거 실측: [Gemma](docs/gemma_evaluation/README.md), [Qwen](docs/qwen_evaluation/README.md), [Vision](docs/vision_evaluation/README.md), [STT](docs/stt_evaluation/README.md)
