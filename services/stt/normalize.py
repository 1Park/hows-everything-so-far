"""Normalize Whisper transcripts before they reach the UI review step and Qwen.

Owned by the STT layer (audio preprocessing / STT model belong to the STT owner).
It only fixes drink names Whisper commonly mishears; it does not interpret intent.

- Maps known mis-hearings and synonyms to the canonical menu (ALIASES), case-insensitively.
- Fuzzy-matches near-miss words to menu items ("cofee" -> "coffee"), guarded so ordinary
  words ("later", "cook") are never rewritten.
- Strips Whisper tags such as [BLANK_AUDIO] and collapses whitespace.
- Keeps the rest of the sentence (including casing) untouched for the customer review screen.

The menu must stay in sync with app/language.py (water, coke, coffee, orange juice).
"orange juice" stays two words in the text; items reports it as orange_juice.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

MENU: tuple[str, ...] = ("water", "coke", "coffee")
PHRASES: dict[str, str] = {"orange juice": "orange_juice"}  # multi-word menu items

# Longer keys are applied first, so "coca cola" wins over "coca".
ALIASES: dict[str, str] = {
    "coca-cola": "coke",
    "coca cola": "coke",
    "coca": "coke",
    "cola": "coke",
    "colas": "coke",
    "cokes": "coke",
    "coffees": "coffee",
    "waters": "water",
    "orange juices": "orange juice",
    "o.j.": "orange juice",
    "oj": "orange juice",
}

# Words that look close to a menu item but must never be rewritten.
FUZZY_STOPWORDS: frozenset[str] = frozenset(
    {"later", "what", "wait", "waiter", "cook", "cookie", "cold", "could", "toffee", "copy"}
)
FUZZY_CUTOFF = 0.85
FUZZY_MIN_LEN = 4

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_TAGS = re.compile(r"\[(?:blank_audio|music|noise|silence)\]|\((?:music|noise|silence)\)", re.I)


@dataclass(frozen=True)
class Normalized:
    raw: str
    text: str
    items: list[str] = field(default_factory=list)


def _apply_aliases(text: str) -> str:
    for key in sorted(ALIASES, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(key)}\b", ALIASES[key], text, flags=re.I)
    return text


def _fuzzy_word(match: re.Match) -> str:
    word = match.group(0)
    lower = word.lower()
    if lower in MENU or lower in FUZZY_STOPWORDS or len(lower) < FUZZY_MIN_LEN:
        return word
    hit = difflib.get_close_matches(lower, MENU, n=1, cutoff=FUZZY_CUTOFF)
    return hit[0] if hit else word


def normalize(raw: str) -> Normalized:
    text = _TAGS.sub(" ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = _apply_aliases(text)
    text = _WORD.sub(_fuzzy_word, text)
    marked = text
    for phrase, item in PHRASES.items():
        marked = re.sub(rf"\b{phrase}\b", item, marked, flags=re.I)
    items = [w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z_'-]*", marked) if w.lower() in (*MENU, *PHRASES.values())]
    return Normalized(raw=raw, text=text, items=items)


if __name__ == "__main__":
    import sys

    for line in sys.argv[1:] or [" No juice, coca, please\n"]:
        result = normalize(line)
        print(f"{result.raw!r} -> {result.text!r} items={result.items}")
