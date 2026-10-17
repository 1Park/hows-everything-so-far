# How's Everything So Far — Refill Assist

On-device drink monitoring and refill assistance, with customer confirmation.

여러 컵·접시를 검출하고 객체별 종류·잔량을 판단한 뒤, 리필 요청을 해석하고 고객 확인을 받아 LED·mock 주방 복귀로 연결하는 4인 해커톤 프로젝트다. 메인 데모는 water / coke / coffee이며, DINOv2와 Qwen3-0.6B를 Arduino VENTUNO Q에서 ExecuTorch로 실행하는 것이 목표다.

## 문서

- [그림으로 보는 아키텍처](docs/architecture.html) — HTML을 브라우저에서 열어 컵 이미지·모델 호출·고객 확인 흐름을 단계별로 탐색
- [아키텍처 및 개발 방식](docs/ARCHITECTURE.md) — 현재 합의한 구조·통신·실행 위치·분업
- [기존 Design Doc](<docs/Design Doc.md>) — 과거 기획 초안; 최신 결정은 아키텍처 문서 우선
- [Qwen 평가 자료](docs/qwen_evaluation/README.md)
- [보드 / ExecuTorch 가이드](qc-executorch-guide/IoT/README.md)

## 레포 구조와 코드 위치

하나의 레포에서 앱·모델 서버·모델 개발 도구를 관리한다. **프로덕션 앱은 보드 Ubuntu에서 직접 실행하고, 모델 학습·QNN용 export 환경은 `ml/`로 분리**한다. 카메라·NPU·Bridge 접근을 위해 앱을 컨테이너에 넣지는 않는다. 모델 개발용 Docker가 앱 배포 방식에 영향을 주지는 않는다.

아래 폴더는 README로 역할을 정의한 초기 구조다. `Dockerfile`, 의존성 파일, Python 모듈, 실행 스크립트는 실제 환경을 확인하며 구현할 예정이고 아직 없다.

```text
app/                   Controller 서버·상태 머신·정책·클라이언트
  ui/                  실제 시연 웹 UI·브라우저 오디오
  hardware/            Controller 내부 Mock / Bridge HardwareIO
services/              보드에서 독립 실행하는 FastAPI 모델 서버
  vision/              카메라·영상·검출·crop·DINO 추론·후처리
  qwen/                Qwen 추론 서버·ExecuTorch 실행 adapter
common/                공통 schema·설정 로더·가벼운 공유 코드
firmware/              MCU용 Arduino sketch·LED·버튼·센서
ml/                    학습·평가·양자화·.pte export 도구
  configs/             모델·학습·전처리·export 설정
  training/            학습·fine-tuning 코드
  evaluation/          이미지 모델의 오프라인 평가 코드
  export/              보드용 변환·검증·배포 bundle 생성
models/                로컬 가중치·.pte·tokenizer·배포 bundle (Git 제외)
data/                  로컬 원본·라벨·학습/검증 데이터 (Git 제외)
fixtures/              팀이 공유하는 작은 샘플·모델 응답 JSON
scripts/               로컬 실행·보드 시작/종료·진단 도구
docs/                  아키텍처·설명 HTML·평가 기록
qc-executorch-guide/   참조용 대회 가이드·예제
```

| 무엇을 만들 때 | 넣을 위치 |
| --- | --- |
| 리필 정책·요청 검증·확인/취소·상태 머신 | `app/` |
| Vision/Qwen HTTP 호출·영어 프롬프트·요청 파싱 | `app/`의 client / language 모듈 |
| 카메라 영상·bbox·요청 카드·확인 버튼·소리 | 브라우저는 `app/ui/`, 영상 획득·송출은 `services/vision/` |
| 실제 DINO/Qwen 모델 로딩·runner 호출·추론 | 해당 `services/vision/` 또는 `services/qwen/` |
| Python에서 LED·센서 mock / Bridge 호출 | `app/hardware/` |
| MCU에서 실행하는 GPIO·시퀀스 | `firmware/` |
| API 양쪽이 공유하는 입력·출력 타입 | `common/` |
| 학습용 Dockerfile·별도 ML 의존성 | `ml/` — 주최 측 지원 환경 확인 후 작성 |
| 학습·이미지 평가·양자화·export 코드 | `ml/`의 해당 하위 폴더 |
| 원본 사진·학습 데이터·가중치·변환 산출물 | `data/`, `models/` — Git 제외, 경로·획득 방법만 문서화 |
| 개발용 작은 재현 샘플 | `fixtures/` — fixture임을 명시 |
| 앱·보드 실행/종료·설치 점검 | `scripts/` |
| 과거 Qwen 발화 평가 원본·재현 안내 | `docs/qwen_evaluation/` — 기존 아카이브 보존 |

학습·평가·export는 `ml/`에서 수행하고, 생성한 bundle을 `models/`에 둔다. 보드 서비스는 bundle만 로드하며 학습 코드·학습용 Docker·전체 데이터셋에 의존하지 않는다. 실제 Vision/Qwen 서버와 Controller의 자세한 경계는 각 폴더 README와 [아키텍처](docs/ARCHITECTURE.md)를 따른다.

## 초기 개발 설정

개인 개발은 `.env.example`을 `.env`로 복사한다.

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```sh
cp .env.example .env
```

기본 개발 구성은 로컬 Controller·UI, Vision fixture, 공용 Mac mini Qwen (`http://won-macmini:8000`), mock 하드웨어다. 공용 서버 접속에는 Tailscale 연결과 이름 해석이 필요하다.

UI·Controller 담당자는 fixture로 개발하고, Vision 담당자는 실제 검출·crop·DINO 파이프라인을 개발한다. Vision API가 준비되면 담당자 기기 또는 Mac mini의 공용 API로 연결할 수 있다. 서버 코드 작성은 로컬에서 진행하고, 실제 ExecuTorch·QNN·카메라·Bridge 연결은 보드에서 초반부터 검증한다.

보드는 커밋된 [`.env.board`](.env.board)를 사용한다. Controller/UI는 8080, Qwen은 8000, Vision은 8001을 기본 포트로 예약한다. 모델 API는 보드 내부 localhost로 연결한다. 개인 `.env`와 비밀 정보는 커밋하지 않는다.

## 서버·배포 방향

서버는 **FastAPI + Uvicorn**, 모델 실행은 **ExecuTorch**로 분리한다. 보드는 **Docker 없이 Ubuntu에서 직접 실행**하며 Python 가상환경을 사용한다. 기존 Mac mini MLX 서버는 그대로 호출한다.

로컬은 `python scripts/dev.py` 하나로 필요한 서버만 시작하고 함께 종료하는 도구를 만들 예정이다. 기본 로컬 실행은 Controller/UI만 필요하며 Mac Qwen 서버는 다시 띄우지 않는다. 보드는 `scripts/start-board.sh`·`scripts/stop-board.sh`로 Controller·Vision·Qwen을 관리할 계획이다. **이 실행 도구들은 아직 구현되지 않았다.** 세부 실행·모델 adapter 계획은 [아키텍처 문서](docs/ARCHITECTURE.md)를 참고한다.

현재 레포는 문서·평가 자료·환경 설정을 준비한 상태다. 앱, 환경 파일 로더, 서버 시작 명령, 의존성 manifest는 아직 구현되지 않았으며 `.env` 파일만으로 서버가 실행되지는 않는다. 구현 시 프로세스 환경변수를 선택한 환경 파일보다 우선하도록 한다.
