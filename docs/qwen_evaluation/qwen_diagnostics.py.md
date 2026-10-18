# qwen_diagnostics.py

Original path: `evaluation/qwen_diagnostics.py` · Original SHA-256: `f7f1c2b6035239842341913246fafc3d895dfda1fddcde4f40443c79a712a742`

The original content is preserved in the code block below. See the [evaluation index](README.md) for how to restore it as an executable file. Line endings may have been normalized when it was stored as Markdown.

````python
import json
import pathlib
import time
import urllib.request


PROBES = [
    ("echo_utf8", "Repeat the user's text exactly. No other text.", "김치 말고 콩나물 조금만 주세요", False),
    ("echo_ascii_escape", "Repeat the user's text exactly. No other text.", "김치 말고 콩나물 조금만 주세요", True),
    ("korean_item", "고객이 요청하는 음식만 답하세요. 김치 또는 콩나물 또는 밥 중 하나만 출력하세요.", "김치 말고 콩나물 주세요", False),
    ("english_item", "Output only the requested food: kimchi, bean_sprouts, or rice.", "Not kimchi. Bean sprouts please.", False),
    ("korean_cancel", "고객이 리필을 원하면 YES, 거절하면 NO만 출력하세요.", "아니요, 아직 먹고 있어요", False),
    ("english_cancel", "Output YES if the customer wants a refill, otherwise NO.", "No thanks, I am still eating.", False),
]


def main():
    rows = []
    for name, system, user, ascii_escape in PROBES:
        payload = {"model": "mlx-community/Qwen3-0.6B-4bit", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0, "max_completion_tokens": 128, "stream": False, "chat_template_kwargs": {"enable_thinking": False}}
        request = urllib.request.Request("http://won-macmini:8000/v1/chat/completions", data=json.dumps(payload, ensure_ascii=ascii_escape).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"})
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        rows.append({"name": name, "request": payload, "ascii_escape": ascii_escape, "response": result, "elapsed_s": time.perf_counter() - started})
    path = pathlib.Path(__file__).parent / "qwen_diagnostics.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=True))


if __name__ == "__main__":
    main()
````
