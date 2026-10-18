# Qwen 평가 기록

이 폴더는 과거 실행의 프롬프트·raw 응답·시간·분석을 보존한다. 이전 음식 메뉴와 portion/clarify 스키마가 포함되므로 현재 제품 계약·정확도의 기준으로 사용하지 않는다. 현재 프롬프트는 [`app/language.py`](../../app/language.py), 재실행은 [`scripts/evaluate_qwen.py`](../../scripts/evaluate_qwen.py)다.

## 음료 평가 (2026-10-17, 이전 스키마)

- [17/20 결과](drinks-20261017T061614204547Z.json): 우리 proxy → Mac MLX, HTTP 중앙값 0.679초.
- [첫 평가 15/20](drinks-20261017T060722867674Z.json), [초기 transport 계약 실패](drinks-20261017T060535441028Z.json).
- [보드 상주 worker raw](resident-worker-20261017.json), [해석·조건](../RESIDENT_LLM.md).

이 데이터는 개발 프롬프트 보완에 사용됐으며 held-out 일반화 결과가 아니다. Mac HTTP 시간은 보드 NPU 지연과 구분한다.

## 이전 음식·STT 유사 왜곡 실험

- [영어 평가](QWEN_ENGLISH_EVALUATION.md), [합성 STT 치환 평가](QWEN_STT_EVALUATION.md), [한국어/혼합 평가](QWEN_EVALUATION.md).
- [영어 프롬프트·케이스](english_cases.py.md), [평가 요청 코드](refill_qwen_eval.py.md), [STT 케이스 생성](stt_cases.py.md).
- [영어 raw](qwen_english_results.json.md), [분석](qwen_english_analysis.json.md), [STT manifest](stt_manifest.json.md), [STT raw](qwen_stt_results.json.md), [쌍별 분석](qwen_stt_analysis.json.md).
- [아카이브 전체 목록·이전 전 hash](MIGRATION.md).

`.py.md`/`.json.md`는 단일 4-backtick 블록에 원문을 보관한 아카이브이며 실행 파일이 아니다. 필요하면 블록 본문을 별도 실험 경로에 복원한다. 기록된 hash는 이전 전 바이트 기준으로, Markdown 줄바꿈 정규화 후 hash와 다를 수 있다. 원본 결과는 덮어쓰지 않고 새 평가는 timestamp 파일로 남긴다.
