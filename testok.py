import time
import requests
import json

URL = "http://localhost:1337/v1/chat/completions"
MODEL = "gemma-31b"  # change to your model name

payload = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "Write 300 words about AI"}],
    "stream": True,
    "max_tokens": 400
}

start = None
total_chars = 0

with requests.post(URL, json=payload, stream=True) as r:
    for line in r.iter_lines():
        if line:
            try:
                data = json.loads(line.decode("utf-8"))
                # Depending on Jan API, streamed chunks have this structure:
                # {"id":..., "object":"chat.completion.chunk", "choices":[{"delta":{"content":"text"}}]}
                for choice in data.get("choices", []):
                    delta = choice.get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        if start is None:
                            start = time.time()
                        total_chars += len(text)
            except json.JSONDecodeError:
                # ignore empty lines or keep-alive signals
                continue

end = time.time()

tokens = total_chars / 4  # rough token estimate
tps = tokens / max((end - start), 1e-6)  # avoid divide by zero

print(f"Tokens/sec: {tps:.2f}")