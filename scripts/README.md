# Execution and diagnostics

모델·제품 로직 대신 실행·배포·진단을 조율하는 도구를 둔다. 아래 이름은 계획이며 아직 실행 파일이 없다.

| 예정 파일 | 역할 |
| --- | --- |
| `dev.py` | `.env` 기반으로 필요한 로컬 서버만 시작. 기본 Controller/UI + 원격 Mac Qwen + Vision fixture. Ctrl+C로 시작한 자식 프로세스 종료 |
| `start-board.sh` | `.env.board`로 Controller·Vision·Qwen 직접 시작, 프로세스별 로그·중복 실행 방지·시작 실패 처리 |
| `stop-board.sh` | 이 앱의 실행 도구가 시작한 프로세스만 종료 |
| 보드 진단 도구 (이름 미정) | OS/CPU·Python·모델/runner·QNN 라이브러리·카메라·Bridge 상태 수집 |
| 모델 smoke 도구 (이름 미정) | 실제 runner에 입력 하나를 전달하고 출력·실행 시간·오류 수집 |

보드 runtime과 호환되는 가상환경·모델 경로를 사용한다. 로컬 서버의 bind와 원격 API 호출 주소를 구분하고, URL이 설정되어 있다는 이유로 로컬 모델 서버를 자동 실행하지 않는다. 시작 도구는 호스트 `arduino-router`나 MCU 펌웨어의 생명주기를 대신 관리하지 않는다.

학습·export는 `ml/`의 도구가 담당한다. 로그·PID·임시 출력은 Git에서 제외한 `logs/`·`tmp/`에 둔다.
