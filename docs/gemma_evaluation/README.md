# Gemma 평가 기록

2026-10-17 보드 HTTP 평가다. **portion/clarify를 쓰던 이전 프롬프트·스키마**의 결과이며 현재 intent/item/not_understood 계약으로 재평가한 결과가 아니다.

| 모델 | 원본20 | 합성 왜곡20 | HTTP 시간 중앙값 (원본 / 왜곡) |
| --- | --- | --- | --- |
| Gemma4 | 16/20 | 15/20 | 1.975초 / 1.781초 |
| Gemma3 | 0/20 | 0/20 | 원본 기록 참조 |

Gemma3는 40개 모두 출력 계약 검증에 실패했고 34개는 user 입력 JSON을 그대로 반환했다. Markdown fence 자체가 주된 실패 원인은 아니다. 이 관찰만으로 모델과 서빙 template 중 어느 쪽이 원인인지 확정하지 않는다. 기본 보드 모델·자동 평가는 Gemma4이며 Gemma3 명시 실행 코드는 남아 있다.

- [전체 프롬프트·케이스별 input/output/소요 시간](drinks-20261017T230141554405Z.md)
- [원본 HTTP 응답·통계·요청 JSON](drinks-20261017T230141554405Z.json)
- 현재 평가셋: [원본20](../../fixtures/drink_cases.json), [합성 왜곡20](../../fixtures/drink_cases_distorted.json)
- 재실행: [`evaluate_gemma.py`](../../scripts/evaluate_gemma.py), 기본 URL은 PC 터널 `127.0.0.1:18000`, 기본 모델은 Gemma4.

당시 PC → SSH 터널 → 보드 localhost:8000을 순차 호출했다. 실제 오디오·이미지 평가가 아니며 왜곡 문장은 합성 텍스트다. 이전 결과의 기대값·요청은 raw 파일에 보존하며 현재 fixture와 다를 수 있다. 새 평가도 input/output/시간을 신규 JSON·Markdown으로 저장한다.
