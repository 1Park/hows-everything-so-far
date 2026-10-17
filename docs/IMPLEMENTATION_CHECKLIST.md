# 보드 수령 전 구현·검증 체크리스트

사용자의 전체 구현 지시를 추적한다. 완료 표시는 실제 검증 근거가 있을 때만 한다.

- [x] 1. 앱 manifest·버전 고정·가상환경, env 우선순위/검증, 구조화 로그/요청 ID/오류 schema, Git 제외
- [x] 2. scene/object/request·bbox·음료/잔량/분량·확인/취소/이벤트, 모델/Controller HTTP·WS 계약
- [x] 3. 관찰→정책→제안→입력→카드→명시 확인→mock 적재/복귀→완료, skip·수정·거절·취소·무응답·재시도
- [x] 3. 오래된/중복 확인·장면 변경·취소/늦은 결과 경쟁 차단, 추론 중 UI 응답
- [x] 4. 독립 Qwen FastAPI, MLX/fixture/ExecuTorch 경계, 제한 queue/timeout/readiness, 영어 프롬프트/엄격 JSON
- [x] 4. Controller→우리 Qwen→실제 Mac 경로, temperature=0 음료 평가셋·새 결과·기존 아카이브 보존
- [x] 5. Vision/STT 서비스 API·schema·backend/fixture/external adapter·입력 제한·timeout·readiness
- [x] 5. 모델 검출/crop/DINO/STT 전후처리 제외, 영상/이미지/오디오 전달·단일 소유 책임 문서
- [x] 6. 실제 영어 UI·영상/bbox/ID/잔량·고정 대상 카드·녹음/STT·확인/취소·복구·고정 오디오·반응형
- [x] 7. 상태 mock·Bridge adapter·LED/버튼/센서/시퀀스 계약·nonblocking 취소 MCU 초안·미검증 표시
- [x] 8. 단일 로컬 명령/종료·직접 Mac/우리 proxy 모드·보드 로그/중복/실패 처리·진단/runner smoke
- [x] 검증: 정상/수정/거절/취소/모호/충분/불확실, malformed/API 장애/timeout/중복/오래된 확인/늦은 결과
- [x] 검증: 실제 서버 통합, 실제 브라우저 UI/영상/bbox/오디오/반응형, 시작→데모→종료→재시작→데모
- [x] 정리: README/폴더 문서/아키텍처/설명 HTML 최종 일치, 외부 blocker·보드 잔여 작업 기록
- [ ] 정리: 테스트/서버 프로세스 종료, Git commit/push

고정 범위: 4인/VENTUNO Q 1대, DINOv2/Qwen3-0.6B, water/coke/coffee, FastAPI/Uvicorn/Ubuntu/venv/localhost. ROS·앱 Docker·실제 주행/집기 없음. Vision/STT 모델은 다른 담당자 소유. 제품 영어. fixture와 실제 추론을 혼동하지 않음.

검증 근거는 [VALIDATION.md](VALIDATION.md), API/담당자 연결은 [CONTRACTS.md](CONTRACTS.md), 태블릿 요구사항은 [TABLET_DEMO.md](TABLET_DEMO.md). 위 체크는 보드 전 범위 기준이며 보드/물리 태블릿 실기 미검증을 완료로 바꾸지 않는다.
