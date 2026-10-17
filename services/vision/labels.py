"""모델 내부 클래스 확률 → 공개 계약 필드 (item, fill_ratio, confidence).

내부 클래스 이름 규칙: "<drink>__<level>" (예: "coke__low") 또는 "empty".
  item       : drink별 확률을 합한 marginal의 최댓값. empty가 가장 크면 "unknown".
  fill_ratio : level별 대표 비율의 기대값 Σ p(class)·ratio(level). 계약은 0..1 연속값이라 단계 라벨을 비율로 바꾼다.
  confidence : min(item marginal 최댓값, level marginal 최댓값) — 종류·잔량 둘 다 확신할 때만 높다.
Controller 정책(confidence ≥ 0.7, fill_ratio ≤ 0.3)은 이 값을 그대로 쓴다.
"""

DRINKS = ("water", "coke", "coffee")
# 단계 → 대표 잔량 비율. full/mid/low 구간(합성 데이터 생성 기준)의 중앙값 근처. bundle.json 으로 덮어쓸 수 있다.
DEFAULT_FILL_RATIO = {"full": 0.85, "mid": 0.5, "low": 0.18, "empty": 0.02}


def parse(label):
    if label == "empty":
        return "unknown", "empty"
    drink, _, level = label.partition("__")
    return (drink if drink in DRINKS else "unknown"), level


def to_observation(probs, classes, fill_ratio=None):
    ratio = {**DEFAULT_FILL_RATIO, **(fill_ratio or {})}
    item_p, level_p, fill = {}, {}, 0.0
    for p, c in zip(probs, classes):
        item, level = parse(c)
        item_p[item] = item_p.get(item, 0.0) + float(p)
        level_p[level] = level_p.get(level, 0.0) + float(p)
        fill += float(p) * ratio.get(level, 0.5)
    item = max(item_p, key=item_p.get)
    conf = min(item_p[item], max(level_p.values()))
    return dict(item=item, fill_ratio=round(min(max(fill, 0.0), 1.0), 4), confidence=round(min(max(conf, 0.0), 1.0), 4))
