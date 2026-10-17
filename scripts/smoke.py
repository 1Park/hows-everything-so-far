"""Real Controller HTTP workflow, including stale/duplicate confirmation protection."""

import argparse
import json
import time

import httpx


def run(url):
    c = httpx.Client(base_url=url, timeout=25, trust_env=False)

    def wait(phase):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            s = c.get("/api/state").json()
            if s["phase"] == phase:
                return s
            if s["phase"] == "error":
                raise AssertionError(s)
            time.sleep(0.05)
        raise AssertionError(s)

    r = c.post("/api/observe", data={"scenario": "normal"})
    r.raise_for_status()
    s = wait("offered")
    identity = {"scene_id": s["scene"]["scene_id"], "object_id": s["target"]["object_id"]}
    c.post(
        "/api/utterance", json={**identity, "utterance": "A little water, please"}
    ).raise_for_status()
    s = wait("card")
    assert s["card"]["item"] == "water", s
    assert c.get("/api/hardware").json()["phase"] in ("idle", "cancelled", "done")
    old = {k: v for k, v in s["card"].items() if k not in ("item",)}
    c.post(
        "/api/utterance", json={**identity, "utterance": "A regular coffee instead, please"}
    ).raise_for_status()
    s = wait("card")
    assert s["card"]["item"] == "coffee", s
    assert c.post("/api/confirm", json=old).status_code == 409
    confirm = {k: v for k, v in s["card"].items() if k not in ("item",)}
    c.post("/api/confirm", json=confirm).raise_for_status()
    assert c.post("/api/confirm", json=confirm).status_code == 409
    s = wait("done")
    result = {
        "done": True,
        "qwen_source": s["qwen_source"],
        "vision_source": s["scene"]["source"],
        "hardware": c.get("/api/hardware").json(),
    }
    # STT transport is explicit fixture output, not real speech recognition.
    import io
    import wave

    audio = io.BytesIO()
    with wave.open(audio, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 1600)
    result["stt"] = c.post(
        "/api/transcribe", files={"file": ("sample.wav", audio.getvalue(), "audio/wav")}
    ).json()
    for scenario in ("enough", "uncertain"):
        c.post("/api/observe", data={"scenario": scenario}).raise_for_status()
        assert wait("skipped")["card"] is None
    c.close()
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    run(parser.parse_args().url)
