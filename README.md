# How’s Everything So Far — Refill Assist

여러 컵·접시의 종류/잔량을 관찰하고, 고객 요청을 해석한 뒤 **명시적 확인을 받아 mock 적재·주방 복귀**를 시연하는 4인 해커톤 프로젝트다. 목표 보드는 Arduino VENTUNO Q 한 대, 비전 DINOv2, 요청 해석 Qwen3-0.6B, 주요 음료 water/coke/coffee다. UI·스피커는 태블릿 브라우저, 마이크 녹음은 보드가 담당한다.

현재 보드 없이 실행 가능하다. 기본은 **Vision/STT fixture + 실제 Mac Qwen HTTP + mock HardwareIO**. Vision/STT 모델 자체는 다른 팀원 소유이며 이 레포 구현은 서비스 계층이다. 보드 ExecuTorch/카메라/Bridge 실기 검증은 별도다. fixture 결과를 실제 인식으로 표시하지 않는다.

## 바로 실행

Python **3.11–3.13** (로컬 검증 3.13), Tailscale로 Mac mini에 연결한다. 레포 루트에서:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -c requirements.lock -e '.[dev]'
Copy-Item .env.example .env
.venv/Scripts/python.exe scripts/dev.py
```

macOS/Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev]'
cp .env.example .env
python scripts/dev.py
```

`http://127.0.0.1:8080` → Start demo → Record request(또는 텍스트) → 전사 검토·Send → 카드 → Confirm refill. 종료 Ctrl+C. 다른 터미널에서 `python scripts/dev.py --stop`도 가능하다. 프로세스 환경변수 > 선택 dotenv(`--env-file`/REFILL_ENV_FILE, 기본 .env) > 기본값. 비밀은 개인 환경에만 저장한다.

| 모드 | 명령 | 이 기기에서 시작하는 프로세스 |
| --- | --- | --- |
| 기본 direct | `python scripts/dev.py` | Controller/UI만. Mac API 직접 호출, Vision/STT fixture |
| 개발 fixture | `python scripts/dev.py --mode fixture` | Controller/UI만. Vision/STT fixture·Hardware mock, Qwen은 설정한 실제 HTTP API |
| 완전 offline | `python scripts/dev.py --mode offline` | Controller/UI만. Qwen 포함 모든 모델 fixture, Hardware mock |
| 우리 Qwen proxy | `python scripts/dev.py --mode proxy` | Controller + Qwen API; Qwen API→실제 Mac |
| 서버 간 통합 | `python scripts/dev.py --mode integration` | Controller + Qwen + Vision + STT; Vision/STT 기본 fixture backend |
| 보드 준비 | `bash scripts/start-board.sh` | .env.board 기반4개 서버. native runner·모델·길이 미설정이면 /ready 503 |

Mac endpoint `http://won-macmini:8000/v1/chat/completions`, 모델 `mlx-community/Qwen3-0.6B-4bit`. 서버 설정/모델을 변경하지 않는다. proxy와 원격 Mac은 서로 다른 기기의8000포트다. 모델 장애 시 fixture로 자동 대체하지 않는다. 평가는 temperature=0.

태블릿은 HTTP로 접속 가능하다. **태블릿 안내 재생 완료 → 보드 마이크 녹음 → STT → Qwen → 확인 카드**가 자동으로 이어진다. 고정 안내 WAV를 재생하며 live TTS는 없다. 초기 Enable sound 동작은 브라우저 스피커 활성화에만 필요하다. [보드 마이크·태블릿 연결 및 실행](docs/TABLET_DEMO.md). 개발용 브라우저 녹음을 선택하는 경우에만 HTTPS가 필요하다.

## 실행·검증

```sh
python -m pytest -q
python -m ruff check app common services scripts tests
python scripts/dev.py --mode integration
# 별도 터미널
python scripts/smoke.py
python scripts/evaluate_qwen.py --proxy
```

실제 Chromium 검증(선택 Node.js): `npm ci`, `npx playwright install chromium`, 실행 중 앱에 `npm run test:browser`. 시스템 Chrome을 쓰면 CHROME_PATH를 지정한다. 테스트 가상 마이크는 오디오 전달 검증이며 실제 STT 정확도 증거가 아니다. 결과·스크린샷은 tmp/browser-qa, 서비스별 로그는 logs. 평가 결과는 docs/qwen_evaluation/drinks-타임스탬프.json에 새 파일로 저장한다.

선택 영상 재생·USB 카메라: `python -m pip install -e '.[camera]'`, CAMERA_SOURCE에 파일 절대경로 또는 USB index 지정. 기본은 AI-generated sample 이미지다. Controller가 입력을 한 번만 열고 MJPEG와 Vision 분석으로 분기한다. 업로드 이미지는 원본 그대로 전달하며 모델 전처리를 구현하지 않는다.

## 레포 구조와 코드 위치

| 위치 | 책임 |
| --- | --- |
| app/ | Controller 상태·정책·클라이언트·영어 프롬프트·검증·미디어 transport |
| app/ui/ | 실제 태블릿/데스크톱 UI·브라우저 녹음/재생·고정 안내 음성 |
| app/hardware/ | 상태 mock/simulator와 미검증 Bridge adapter |
| services/qwen/ | 독립 FastAPI 생성 서버·MLX/fixture/ExecuTorch 경계 |
| services/vision/, services/stt/ | API·backend interface·fixture·외부 담당자 연결, 모델 코드는 제외 |
| common/ | 공통 schema·설정·로그·오류·제한 queue·transport 검증 |
| firmware/ | MCU mock 시퀀스 초안, 별도 빌드/업로드·미검증 |
| ml/configs/, training/, evaluation/, export/ | 학습·평가·양자화·.pte export와 별도 ML Docker 관심사 |
| models/, data/ | 로컬 모델/대량 데이터, README 외 Git 제외 |
| fixtures/ | 명시적 fixture JSON·음료 텍스트 평가셋 |
| scripts/ | 로컬 supervisor·보드 시작/종료·진단·runner smoke·평가·검증 |
| tests/ | 정책/경쟁/계약/API 테스트 |
| docs/ | 아키텍처·API 계약·태블릿/보드 안내·검증 기록 |
| qc-executorch-guide/ | 대회 제공 참조 가이드·artifact inventory |

로컬/보드 모델 파일 배치와 실제 backend 연결 작업은 [모델 연결 가이드](models/README.md)를 따른다. 다른 개발자나 코딩 AI는 구현 전에 이 가이드와 담당 서비스 README를 읽는다. `models/local/`·`models/board/` 및 모델 경로 환경변수는 연결 시 따를 규칙이며, 현재 자동 파일 로더가 구현됐다는 뜻은 아니다.

앱은 **ROS·배포 Docker 없이 Ubuntu + venv + FastAPI/Uvicorn**. 학습/export Docker는 ml/에 분리한다. 모델 bundle/라이브러리는 별도 설치하고 새 표준 버전으로 임의 교체하지 않는다.

## 문서

- [아키텍처](docs/ARCHITECTURE.md), [그림으로 보는 설명](docs/architecture.html) (실제 UI는 앱의 `/`)
- [API·담당자 연결 계약](docs/CONTRACTS.md), [태블릿 데모](docs/TABLET_DEMO.md)
- [보드 통합 준비](docs/BOARD_RUNBOOK.md), [검증 결과·남은 작업](docs/VALIDATION.md)
- [요구사항 체크리스트](docs/IMPLEMENTATION_CHECKLIST.md), [Qwen 평가](docs/qwen_evaluation/README.md)
- [과거 Design Doc](<docs/Design Doc.md>) (최신 결정은 아키텍처 우선)


<!-- Native runner implementation status -->
### Native ExecuTorch runner status

Qwen's former placeholder now invokes the QC native runner via
`common/backends.py:ExecuTorchBackend`; configure actual runner/model/tokenizer
paths and `QWEN_SEQ_LEN` per [Qwen setup](services/qwen/README.md).
DINOv2 prepared-tensor execution is available as `common.executorch.DinoRunner`
and `scripts/dino_smoke.py`; the Vision owner still supplies all image
preprocessing/detection and output conversion. See [Vision setup](services/vision/README.md).
Earlier references to an unconnected adapter describe missing runtime assets or
remaining board validation, not a missing subprocess implementation.
This is per-request model loading, not a persistent runtime. Tests use a process
double; actual board model loading, template compatibility and NPU execution remain
unverified. Qwen's native limit is total sequence length, not exact completion tokens.
