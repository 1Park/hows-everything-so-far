"""What the assistant says out loud for each state (spoken by the board TTS, played on the tablet).

Short, friendly English lines. The screen keeps its own longer message; speech stays brief so the
board microphone can start recording soon after the offer. None means stay silent.
"""

from common.vision_categories import VISION_CATEGORY_MAP


def say(item):
    return item.replace("_", " ")  # orange_juice -> "orange juice"


def refill_offer(item):
    category = VISION_CATEGORY_MAP.get(item, item)
    if category == "unknown":
        return "How is everything? Can I get you a refill?"
    return f"How is everything? Can I get you some more {say(category)}?"


def speech_for(phase, target, card, item_confirm_threshold, allowed_items=None):
    item = card.item if card else (target.item if target else None)
    if phase == "offered" and target is not None:
        return refill_offer(target.item)
    if phase == "card" and card is not None:
        return f"One more {say(card.item)}, got it. Please press Confirm."
    if phase == "not_understood":
        return "Sorry, I didn't catch that. Could you say that again?"
    if phase == "declined":
        return "No problem. Just call me if you need anything."
    if phase == "cancelled":
        return "Okay, cancelled. Call me anytime."
    if phase == "done" and item:
        return f"Your {say(item)} refill is on its way."
    if phase == "expired":
        return "I'll check back on you later."
    if phase == "error":
        return "Sorry, something went wrong. Please try again."
    return None
