"""모델 내부 클래스 확률 → 공개 계약 필드 (item, fill_ratio, confidence).

내부 클래스 이름 규칙: "<drink>__<level>" (예: "coke__low"), "empty", 또는 "other"(컵이 아닌 물체: 캔·병).
  other    : YOLO가 cup으로 잘못 잡는 물체. split_other()로 먼저 걸러내고, 남은 확률을 정규화해 아래 값을 계산한다.
  item       : drink별 확률을 합한 marginal의 최댓값. empty가 가장 크면 "unknown".
  fill_ratio : level별 대표 비율의 기대값 Σ p(class)·ratio(level). 계약은 0..1 연속값이라 단계 라벨을 비율로 바꾼다.
  confidence : min(item marginal 최댓값, level marginal 최댓값) — 종류·잔량 둘 다 확신할 때만 높다.
  item_confidence : 음료가 있다고 볼 때 "어느 음료인지"만의 확신도 = 최고 음료 marginal / 음료 marginal 합.
                    empty/unknown 확률은 빼고 정규화한다. item 이 unknown 이면 None.
                    coke↔coffee 처럼 음료만 애매한 경우를 Controller가 고객에게 묻는 데 쓴다.
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


OTHER = "other"
OTHER_DROP = 0.5  # p(other) 가 이 이상이면 컵이 아닌 것으로 보고 결과에서 뺀다


def split_other(probs, classes, drop=OTHER_DROP):
    """→ (컵이 아님 여부, other 를 뺀 확률, other 를 뺀 클래스). other 클래스가 없는 head 면 그대로."""
    if OTHER not in classes:
        return False, list(probs), list(classes)
    i = classes.index(OTHER)
    p_other = float(probs[i])
    rest = [float(p) for j, p in enumerate(probs) if j != i]
    cls = [c for j, c in enumerate(classes) if j != i]
    total = sum(rest)
    return p_other >= drop, ([p / total for p in rest] if total > 0 else rest), cls


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
    drink_total = sum(v for k, v in item_p.items() if k in DRINKS)
    item_conf = None
    if item != "unknown" and drink_total > 0:
        item_conf = round(min(max(item_p[item] / drink_total, 0.0), 1.0), 4)
    return dict(item=item, fill_ratio=round(min(max(fill, 0.0), 1.0), 4),
                confidence=round(min(max(conf, 0.0), 1.0), 4), item_confidence=item_conf)
