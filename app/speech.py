"""What the assistant says out loud for each state (spoken by the board TTS, played on the tablet).

Short, friendly English lines. The screen keeps its own longer message; speech stays brief so the
board microphone can start recording soon after the offer. None means stay silent.
"""

from collections import Counter

from common.vision_categories import VISION_CATEGORY_MAP


def say(item):
    return item.replace("_", " ")  # orange_juice -> "orange juice"


def drink_list(items):
    counts = Counter(items)
    names = [say(item) if count == 1 else f"{count} glasses of {say(item)}"
             for item, count in counts.items()]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def refill_offer(items):
    if isinstance(items, str):
        items = [items]
    categories = [VISION_CATEGORY_MAP.get(item, item) for item in items]
    if not categories or "unknown" in categories:
        return "How is everything? Can I get you a refill?"
    if len(set(categories)) < len(categories):
        return f"How is everything? Would you like refills for your {drink_list(categories)}?"
    return f"How is everything? Can I get you some more {drink_list(categories)}?"


def speech_for(phase, target, card, item_confirm_threshold, allowed_items=None):
    requested = drink_list([s.item for s in card.selections] or [card.item]) if card else None
    if phase == "offered" and target is not None:
        return refill_offer(target.item)
    if phase == "card" and card is not None:
        return f"One more {requested}, got it. Please press Confirm."
    if phase == "loading" and card is not None:
        return f"Got it, I'll be right back with {requested}."
    if phase == "not_understood":
        return "Sorry, I didn't catch that. Could you say that again?"
    if phase == "declined":
        return "No problem. Just call me if you need anything."
    if phase == "cancelled":
        return "Okay, cancelled. Call me anytime."
    if phase == "expired":
        return "I'll check back on you later."
    if phase == "error":
        return "Sorry, something went wrong. Please try again."
    return None
