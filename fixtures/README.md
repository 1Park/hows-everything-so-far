# 명시적 개발 fixture

vision.json의 bbox·음료·fill_ratio·confidence는 설명용 AI 사진(docs/assets/cups-example.jpg)에 맞춘 **수동 fixture**. 실제 DINO/검출 결과가 아니다. enough/uncertain 시나리오는 서비스가 fixture 잔량/신뢰도를 바꿔 skip을 재현한다. 임의 업로드 이미지에는 이 bbox가 정합하지 않으며 UI에 fixture임을 알린다.

drink_cases.json은 water/coke/coffee 요청 해석20개, expected intent/item/portion. 프롬프트 보완에 사용하므로 held-out 정확도로 해석하지 않는다. 평가 시 실제 모델 raw와 prompt를 새 timestamp 결과에 저장한다. 기본 STT fixture의 고정 문장은 실제 전사가 아니다. 오류·timeout·late-result는 tests/에서 주입해 검증한다.

`python scripts/dev.py --mode fixture`는 Vision/STT/Hardware fixture + 실제 Qwen HTTP 조합이다. Qwen까지 모델 없이 재현하려면 `--mode offline`을 사용한다.

mock_events.jsonl은 대시보드용 **모의 이력**이다(`scripts/make_mock_events.py`, 고정 seed로 재생성). 저녁 바 가정, 2026-10-11~17 16:00–23:00(America/Los_Angeles, ts는 UTC), 음료 coke/coffee/beer/water/cocktail. detected 100줄(low 50, high 50)과 low 감지 약 30초(20–45초) 뒤 requested 40줄. 형식은 `logs/events.jsonl`과 같고 모든 줄에 `"mock": true`가 있어 실제 기록과 합쳐도 구분된다. beer/cocktail은 앱 메뉴(water/coke/coffee)에 없는 대시보드 전용 값이다.
