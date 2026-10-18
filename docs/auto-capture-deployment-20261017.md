# 자동 캡처 배포 기록

당시 검증 결과이며 현재 실행 안내는 [보드 runbook](BOARD_RUNBOOK.md)을 따른다.

## 보드 배포 확인 (2026-10-17 Pacific)

기능 commit `1ac6e0a`, 팀 최신 변경 병합 `b2de6a0`를 QCVENTUNO002에 반영했다. 병합 후 Controller/HTTP/자동 캡처/보드 음성/Vision 관련 테스트 49개 및 Ruff 통과.

- 기존 direct + with-stt supervisor를 종료 완료까지 기다린 후 재시작했다. Gemma4/Whisper는 재시작하지 않았다.
- 배포 전 Vision 서비스가 worker 경로 누락으로 시작 실패한 상태를 발견했다. 기존 runbook의 `dinov2-qnn-v4c`·실제 `qnn_vision_worker`·QNN 라이브러리 설정으로 복구했다. 모델/전처리는 변경하지 않았다.
- Controller `/ready`=true, Vision/STT source=external, LLM source=executorch 및 Gemma4 resident=true 확인.
- 자동 모드를 5초 미만 켜 실제 카메라→Vision 주기 호출(source=external)을 확인하고 Manual로 복원했다. 당시 검출 객체 0개로 scanning 상태를 유지했고 세션·녹음·하드웨어 동작을 시작하지 않았다. 실물 컵을 놓은 5초 안정성→안내 전체 시연은 별도 현장 확인이 필요하다.
- 실행 중 로그/검증 결과: 보드 `logs/dev-8080.out`, `logs/controller.log`, `logs/auto-capture-deploy-check.json`. 태블릿 http://192.168.50.1:8080/ 새로고침 후 Capture mode → Automatic을 선택한다.
