# stt_cases.py

Original path: `evaluation/stt_cases.py` · Original SHA-256: `c2ea4d87b674b41cb430e1452bffd8c8e1a5bdb3ad0ca81c146d4fbbf825dccf`

The original content is preserved in the code block below. See the [evaluation index](README.md) for how to restore it as an executable file. Line endings may have been normalized when it was stored as Markdown.

````python
import hashlib
import json
import pathlib

from english_cases import SYSTEM_EN, UTTERANCES
from refill_qwen_eval import CASES, HOLDOUT


VARIANTS = [
    ("S01", "simple_01", "Please refill the kim chee.", "kimchi -> kim chee", "menu"),
    ("S02", "simple_01", "Please refill the kin chi.", "kimchi -> kin chi", "menu"),
    ("S03", "simple_02", "Just a little been sprouts, please.", "bean -> been", "menu"),
    ("S04", "simple_02", "Just a little bean spouts, please.", "sprouts -> spouts", "menu"),
    ("S05", "simple_03", "More rise, please.", "rice -> rise", "menu"),
    ("S06", "simple_03", "More rye, please.", "rice -> rye", "ambiguous_menu"),
    ("S07", "simple_04", "A small serving of kim chee, please.", "kimchi -> kim chee", "menu"),
    ("S08", "simple_02", "Just a little been spouts, please.", "bean -> been; sprouts -> spouts", "multiple"),
    ("S09", "english_01", "A small refill of rise, please.", "rice -> rise", "menu"),
    ("S10", "negation_01", "Not kim chee, just a little been sprouts, please.", "kimchi -> kim chee; bean -> been", "multiple"),
    ("S11", "negation_03", "I'm good on been sprouts. A little rise, please.", "bean -> been; rice -> rise", "multiple"),
    ("S12", "english_02", "Knot kimchi. Bean sprouts please.", "Not -> Knot", "negation"),
    ("S13", "cancel_01", "Know, I'm still eating.", "No -> Know", "negation"),
    ("S14", "cancel_03", "Don't bring me kim chee.", "kimchi -> kim chee", "refusal_menu"),
    ("S15", "cancel_05", "I'd like to council the request I just made.", "cancel -> council", "cancel_word"),
    ("S16", "edit_01", "Know, just a small amount.", "No -> Know", "negation"),
    ("S17", "edit_02", "I'll change it to been sprouts.", "bean -> been", "context"),
    ("S18", "holdout_08", "Change it to rise, please.", "rice -> rise", "context"),
    ("S19", "holdout_07", "Change it to a normal potion, please.", "portion -> potion", "portion"),
    ("S20", "ambiguous_04", "Both kim chee and been sprouts, please.", "kimchi -> kim chee; bean -> been", "multiple"),
    ("S21", "ambiguous_06", "A double portion of kim chee, please.", "kimchi -> kim chee", "unsupported"),
    ("S22", "holdout_15", "Council my refill, please.", "Cancel -> Council", "cancel_word"),
    ("S23", "simple_01", "Please re fill the kimchi.", "refill -> re fill", "segmentation"),
    ("S24", "simple_03", "More rice, pleas.", "please -> pleas", "noncritical"),
]


def build_cases():
    originals = {case[0]: (case, UTTERANCES[index]) for index, case in enumerate(CASES + HOLDOUT)}
    pairs = []
    requests = []
    for pair_id, source_id, noisy, changes, category in VARIANTS:
        source, clean = originals[source_id]
        current, answer = source[3], source[4]
        pairs.append({"pair_id": pair_id, "source_id": source_id, "clean": clean, "noisy": noisy, "substitutions": changes, "category": category, "current_request": current, "expected": answer})
        for variant, utterance in [("clean", clean), ("noisy", noisy)]:
            assert utterance.isascii()
            requests.append((pair_id + "_" + variant, variant, utterance, current, answer))
    manifest = {"description": "Synthetic phonetic text substitutions, not outputs of a measured STT engine. Expected labels retain original speaker intent. Some corruptions are ambiguous; abstention is not an unsafe action.", "prompt_sha256": hashlib.sha256(SYSTEM_EN.encode()).hexdigest(), "temperature": 0, "pairs": pairs}
    path = pathlib.Path(__file__).parent / "stt_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return requests
````
