"""Fixed post-softmax category groups; independent of the classifier's weights."""

VISION_CATEGORY_GROUPS = {"water": ("water",), "coke": ("coke", "coffee"), "orange_juice": ("orange_juice",)}
DEMO_CATEGORY_GROUPS = {
    "water": ("water", "sparkling_water", "soda"),
    "coke": ("coke", "coke_zero", "coffee"),
    "orange_juice": ("orange_juice",),
}
VISION_CATEGORY_MAP = {
    member: representative
    for representative, members in VISION_CATEGORY_GROUPS.items()
    for member in members
}


def available_drinks(items, demo=False):
    """Expand observed groups into a deterministic, duplicate-free customer menu."""
    groups = {VISION_CATEGORY_MAP.get(item) for item in items}
    mapping = DEMO_CATEGORY_GROUPS if demo else VISION_CATEGORY_GROUPS
    return [member for name, members in mapping.items()
            if name in groups for member in members]
