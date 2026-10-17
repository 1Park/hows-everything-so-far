# How's Everything So Far — Refill Assist

On-device drink monitoring and refill assistance, with customer confirmation.

여러 컵·접시를 검출하고 객체별 종류·잔량을 판단한 뒤, 리필 요청을 해석하고 고객 확인을 받아 LED·mock 주방 복귀로 연결하는 4인 해커톤 프로젝트다. 메인 데모는 water / coke / coffee이며, DINOv2와 Qwen3-0.6B를 Arduino VENTUNO Q에서 ExecuTorch로 실행하는 것이 목표다.

## 문서

- [그림으로 보는 아키텍처](docs/architecture.html) — HTML을 브라우저에서 열어 컵 이미지·모델 호출·고객 확인 흐름을 단계별로 탐색
- [아키텍처 및 개발 방식](docs/ARCHITECTURE.md) — 현재 합의한 구조·통신·실행 위치·분업
- [기존 Design Doc](<docs/Design Doc.md>) — 과거 기획 초안; 최신 결정은 아키텍처 문서 우선
- [Qwen 평가 자료](docs/qwen_evaluation/README.md)
- [보드 / ExecuTorch 가이드](qc-executorch-guide/IoT/README.md)

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
