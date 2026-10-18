# Multi-cup refill requests

All confident low-fill cups are offered in one sentence: for example, "Can I get you some more water and coke?"
Two water cups are described as "2 glasses of water" and retain distinct object IDs.
Unknown, uncertain, and sufficiently full cups keep their existing skip policy.

For multiple eligible cups, the Controller sends target IDs, observed groups, per-cup allowed drinks, current selections,
and the new utterance to the LLM. The LLM chooses the intent and cup selections:

```json
{"intent":"refill","selections":[{"object_id":"cup-water","item":"water"},{"object_id":"cup-coke","item":"coke"}]}
```

- "Yes please" accepts all current selections; the initial selection includes every offered cup.
- "Water only" selects only the offered water cups. "Both" restores the whole offer after a partial edit.
- "Coffee only" can select the coke-group cup and request coffee. Demo variants use their existing opt-in mapping.
- "No thanks" declines the whole offer with an empty selections array.
- Ambiguous references such as "just one" when two identical cups are offered require clarification.

Every selected ID must belong to the frozen offer and every drink must be allowed for that cup.
The complete selection is validated before any batch starts. Duplicate IDs and stale confirmations are rejected.
Single-cup requests keep the prior scene-wide drink-edit menu for compatibility.

`target` and the card's top-level `object_id` remain the primary ACK/Confirm anchor. The card's
`selections` contains all actual selected cup IDs. UI text, bbox highlighting, TTS, and requested-event
history use these selections. The existing MCU/mock sequence runs once per batch; this change adds
no physical navigation or per-cup dispensing implementation.

Single-cup requests keep the original prompt, `{current_request:{item},allowed_items,utterance}`
input, and `{intent,item}` reply. The Controller maps that reply to the single cup for UI/events.
This avoids changing single-cup model behavior merely because multi-cup support was added.
Legacy `{intent,item}` model replies are accepted for single-cup requests only. An actual model
error is never replaced by the deterministic fixture backend.

## Verification

Fixture Controller tests and a real browser check cover the combined offer, all/subset/none
selections, identical drinks, rejected unknown IDs, card highlights, and mobile layout.
[Actual Gemma evaluation](gemma_evaluation/multi-cup-20261018.json) used temperature 0 and
the production `cup-0`/`cup-1` IDs: five replies selected the expected cups and drinks.
A separate semantic-ID probe (`cup-water`/`cup-coke`) returned coke for "Coffee only";
that model error is preserved alongside the successful production-ID run. This small
evaluation does not guarantee general language accuracy. No board deployment was performed.

[Single-cup regression smoke](gemma_evaluation/single-cup-regression-20261018.json) runs
the local Controller against the actual board LLM at temperature 0 (fixture Vision/mock Hardware):
13 scenarios, 14 model calls, all expected Controller outcomes after restoring the single-cup
prompt. It covers acceptance, drink edits and reacceptance, refusal/cancel, unclear/unsupported
requests, demo variants, and automatic sequence completion. The pre-fix duplicate-ID failure
and raw model outputs are preserved. Out-of-menu model answers are rejected by the Controller.
