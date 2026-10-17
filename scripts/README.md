# 실행·진단

레포 루트/venv에서 실행한다. [전체 설치](../README.md).

| 도구 | 역할 |
| --- | --- |
| dev.py | direct/fixture/proxy/integration/board 모드, 포트·lock 검사, startup 실패 시 자식 정리, 로그 |
| dev.py --stop | matching mode/port supervisor에 종료 요청; --mode board에는 동일 옵션 사용 |
| start-board.sh / stop-board.sh | Linux native background supervisor, PID·중복 검사·실패/종료 대기 |
| diagnose.py | OS/arch/Python, 명시 runner/model/library, camera/Bridge/router read-only 진단 |
| runner_smoke.py -- <실제 runner와 flags> | 단일 입력 실행·시간/출력/오류 logs 기록; CLI를 추측하지 않음 |
| smoke.py | 실제 Controller HTTP를 통해 리필/수정/stale/duplicate/완료/STT/skip 검증 |
| evaluate_qwen.py --proxy | 실제 local proxy→Mac 음료 평가, temperature0, timestamp 신규 결과 |
| browser_check.cjs | 실제 Chromium 녹음/fixtureSTT/고정 오디오/카드/확인/취소/반응형/재연결 |

logs/서비스명.log, tmp/lock은 Git 제외. Ctrl+C 또는 --stop. 외부 Mac 서버·호스트 arduino-router·MCU firmware·Tailscale Serve는 이 supervisor가 시작/종료하지 않는다. board --stop은 shell stop 도구와 같은 managed supervisor만 대상으로 한다.
