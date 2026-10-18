"""Internal model class probabilities → public contract fields (item, fill_ratio, confidence).

Internal class names: "<drink>__<level>" (e.g. "coke__low"), "empty", or "other" (non-cup objects:
cans, bottles).
  other    : objects YOLO wrongly detects as cups. split_other() filters them out first, and the
             remaining probabilities are renormalized before computing the values below.
  item       : argmax of the per-drink marginal probabilities. "unknown" if empty is the largest.
  fill_ratio : expected value Σ p(class)·ratio(level) over per-level representative ratios. The
               contract wants a continuous 0..1 value, so level labels are mapped to ratios.
  confidence : min(drink confidence, level confidence) — high only when both drink and level are sure.
               Level confidence treats low and empty as one group (REFILL_LEVELS). Both mean refill,
               so confusing low↔empty, as with a glass holding a little clear water, does not change
               the refill decision.
               When this group wins, the opposite side is added to drink confidence as well:
               + p(empty) for a drink cup, + Σ p(<drink>__low) for an empty cup (unknown).
               Confusion between low↔full still lowers the score.
  item_confidence : confidence in which drink it is, assuming there is one = top drink marginal /
                    sum of drink marginals. empty/unknown probability is left out before
                    normalizing. None when item is unknown.
                    Measured after category merging (coffee + coke → coke).
Controller policy (default confidence ≥ 0.7, fill_ratio ≤ 0.3 / board .env.board 0.6, 0.35) uses
these values as is.
"""

from common.vision_categories import VISION_CATEGORY_MAP

DRINKS = ("water", "coke", "coffee", "orange_juice")
# level → representative fill ratio, near the middle of each full/mid/low band (as used for
# synthetic data generation). bundle.json can override it.
DEFAULT_FILL_RATIO = {"full": 0.85, "mid": 0.5, "low": 0.18, "empty": 0.02}
REFILL_LEVELS = ("low", "empty")  # levels grouped together for level confidence (both need refill)


def parse(label):
    if label == "empty":
        return "unknown", "empty"
    drink, _, level = label.partition("__")
    return VISION_CATEGORY_MAP.get(drink, "unknown"), level


OTHER = "other"
OTHER_DROP = 0.5  # not a cup (dropped) if p(other) ≥ this or other is the top class


def split_other(probs, classes, drop=OTHER_DROP):
    """→ (not a cup, probs without other, classes without other). Unchanged if the head has no
    other class.

    Drop when other is the top class even below 0.5: on the board, an orange juice glass in front of
    a snack bag gave the bag box other 0.47 / orange_juice__low 0.38, and renormalizing without
    other turned it into an orange juice refill target. On 453 cross-validation cup images this
    rule drops no additional cups.
    """
    if OTHER not in classes:
        return False, list(probs), list(classes)
    i = classes.index(OTHER)
    p_other = float(probs[i])
    rest = [float(p) for j, p in enumerate(probs) if j != i]
    cls = [c for j, c in enumerate(classes) if j != i]
    total = sum(rest)
    not_cup = p_other >= drop or p_other >= max(float(p) for p in probs)
    return not_cup, ([p / total for p in rest] if total > 0 else rest), cls


def to_observation(probs, classes, fill_ratio=None):
    ratio = {**DEFAULT_FILL_RATIO, **(fill_ratio or {})}
    item_p, level_p, fill = {}, {}, 0.0
    for p, c in zip(probs, classes):
        item, level = parse(c)
        item_p[item] = item_p.get(item, 0.0) + float(p)
        level_p[level] = level_p.get(level, 0.0) + float(p)
        fill += float(p) * ratio.get(level, 0.5)
    item = max(item_p, key=item_p.get)
    refill = sum(level_p.get(lv, 0.0) for lv in REFILL_LEVELS)
    level_conf = max([refill] + [v for k, v in level_p.items() if k not in REFILL_LEVELS])
    item_conf_part = item_p[item]
    if refill >= level_conf:  # low/empty side wins: confusion between them does not lower drink confidence either
        if item == "unknown":
            item_conf_part += sum(float(p) for p, c in zip(probs, classes) if c != "empty" and parse(c)[1] == "low")
        else:
            item_conf_part += item_p.get("unknown", 0.0)
    conf = min(item_conf_part, level_conf)
    drink_total = sum(v for k, v in item_p.items() if k in DRINKS)
    item_conf = None
    if item != "unknown" and drink_total > 0:
        item_conf = round(min(max(item_p[item] / drink_total, 0.0), 1.0), 4)
    return dict(item=item, fill_ratio=round(min(max(fill, 0.0), 1.0), 4),
                confidence=round(min(max(conf, 0.0), 1.0), 4), item_confidence=item_conf)
