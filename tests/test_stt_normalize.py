from pathlib import Path

import pytest

from common.api import ApiError
from common.config import Settings
from services.stt.normalize import MENU, normalize

CASES = [
    # (whisper output, expected text, expected items)
    (" No juice, coca, please\n", "No juice, coke, please", ["coke"]),
    (" can I get some more water please?\n", "can I get some more water please?", ["water"]),
    ("Not water, Coca-Cola please.", "Not water, coke please.", ["water", "coke"]),
    ("A cola, please", "A coke, please", ["coke"]),
    ("Coca Cola", "coke", ["coke"]),
    ("Just a little Coke", "Just a little Coke", ["coke"]),
    ("Cofee please", "coffee please", ["coffee"]),
    ("More watter", "More water", ["water"]),
    ("No thanks, I'm good.", "No thanks, I'm good.", []),
    ("Maybe later.", "Maybe later.", []),  # 'later' must not become 'water'
    ("Let me cook", "Let me cook", []),  # 'cook' must not become 'coke'
    ("What?", "What?", []),
    (" [BLANK_AUDIO]\n", "", []),
    ("", "", []),
]


@pytest.mark.parametrize(("raw", "text", "items"), CASES)
def test_normalize(raw, text, items):
    result = normalize(raw)
    assert result.text == text
    assert result.items == items


def test_menu_matches_language_prompt():
    prompt = (Path(__file__).resolve().parents[1] / "app/language.py").read_text()
    assert "item: " + ", ".join(MENU) + ", or null" in prompt


def _mock_whisper(monkeypatch, text):
    import httpx

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            **kwargs,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"text": text})),
        ),
    )


async def test_whisper_http_applies_normalize(monkeypatch):
    from services.stt.whisper_http import WhisperHTTP

    _mock_whisper(monkeypatch, " No juice, coca, please\n")
    result = await WhisperHTTP(Settings(qwen_backend="fixture")).infer(b"audio", "audio/wav")
    assert result.text == "No juice, coke, please"
    assert result.source == "external"


async def test_whisper_http_blank_audio_is_no_speech(monkeypatch):
    from services.stt.whisper_http import WhisperHTTP

    _mock_whisper(monkeypatch, " [BLANK_AUDIO]\n")
    with pytest.raises(ApiError) as error:
        await WhisperHTTP(Settings(qwen_backend="fixture")).infer(b"audio", "audio/wav")
    assert error.value.code == "no_speech"


async def test_whisper_http_non_string_text_is_invalid(monkeypatch):
    from services.stt.whisper_http import WhisperHTTP

    _mock_whisper(monkeypatch, 123)
    with pytest.raises(ApiError) as error:
        await WhisperHTTP(Settings(qwen_backend="fixture")).infer(b"audio", "audio/wav")
    assert error.value.code == "stt_unavailable"
