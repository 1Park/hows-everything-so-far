# 보드 LLM 상주

현재 동작·설정은 [LLM 서비스](../services/qwen/README.md), 실행은 [보드 runbook](BOARD_RUNBOOK.md)을 따른다. Gemma4는 서버 시작 시 생성 호출 없이 preload한다. `/ready`의 `runner.resident/llm/pid`가 실제 로드 상태다.

## 과거 검증 (2026-10-17)

아래는 이전 스키마(portion/clarify)의 QA 기록이며 현재 제품 정확도 결과가 아니다.

- Gemma4 첫 호출 4.505초(load 2.895초), 후속 두 호출 1.569초/1.569초, 동일 worker PID.
- 명시 model ID 전환 검증: Gemma4 첫 호출 5.606초, 재사용 1.863/1.881초, Gemma3 전환 4.418초, Gemma4 복귀 5.272초.
- [원본 응답·통계](qwen_evaluation/resident-worker-20261017.json). 소수 smoke 요청이며 전체 시나리오 정확도·현재 invoke 지연을 보장하지 않는다.

상주 worker 재사용은 대화 이력 재사용과 다르다. 요청마다 KV를 초기화한다. `board_llm.sh ask`는 일회성 CLI 진단이며 HTTP 상주 성능과 구분한다.
