import os, json, time, re
from .utils import log

VISION_PROMPT = (
    "You are a content intelligence engine. Analyze this transcript and extract the core message.\n\n"
    "TRANSCRIPT (Gujarati):\n"
    "TRANSCRIPT_HERE\n\n"
    "Return ONLY valid JSON with exactly these keys:\n"
    '{\n'
    '  "main_topic": "short subject in Gujarati (max 80 chars)",\n'
    '  "core_conflict": "central tension or teaching in Gujarati (1-2 sentences)",\n'
    '  "provocative_angle": "most surprising statement in Gujarati (1 sentence)",\n'
    '  "festival": "festival name if mentioned, else null",\n'
    '  "location": "location if mentioned, else null",\n'
    '  "date": "date if mentioned, else null",\n'
    '  "theme": "one of: victory | celebration | devotional | teaching | announcement"\n'
    '}\n\n'
    "Rules:\n"
    "- Write main_topic, core_conflict, provocative_angle in GUJARATI script.\n"
    "- Base everything strictly on the transcript. No fabrication.\n"
    "- theme must be exactly one of the 5 options."
)


def _call_gemini(api_key, prompt, max_retries=6):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.models.generate_content(
                model   = "gemini-2.5-flash-lite",
                contents= prompt,
                config  = types.GenerateContentConfig(
                    response_mime_type = "application/json",
                    temperature        = 0.3,
                    top_p              = 0.8,
                    max_output_tokens  = 1024,
                ),
            )
            return resp.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                # Daily quota exhausted (limit: 0) — no point retrying
                if "limit: 0" in err:
                    log("VISION", "  Daily quota exhausted — skipping retries, using fallback.")
                    raise RuntimeError("Daily Gemini quota exhausted. Add billing or use a second key.")
                wait = 20 * attempt
                m = re.search(r"retryDelay.*?(\d+)s", err)
                if m: wait = int(m.group(1)) + 5
                log("VISION", f"  429 rate limit — waiting {wait}s (attempt {attempt}/{max_retries}) ...")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Gemini rate-limited after {max_retries} retries.")


def extract_vision(segments, api_key, output_dir="workspace"):
    os.makedirs(output_dir, exist_ok=True)
    transcript = " ".join(
        (s.get("translated") or s.get("text","")).strip()
        for s in segments
    ).strip()
    log("VISION", f"Transcript ({len(transcript)} chars) preview: {transcript[:120]}")
    if not transcript:
        log("VISION", "Empty transcript — fallback."); return _fallback_extract(segments)
    if not api_key:
        log("VISION", "No key — fallback."); return _fallback_extract(segments)
    prompt = VISION_PROMPT.replace("TRANSCRIPT_HERE", transcript)
    try:
        raw = _call_gemini(api_key, prompt)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        data = json.loads(raw.strip())
        valid_themes = {"victory","celebration","devotional","teaching","announcement"}
        if data.get("theme") not in valid_themes: data["theme"] = "teaching"
        log("VISION", f"Topic: {data.get('main_topic','?')} | Theme: {data.get('theme','?')}")
        with open(os.path.join(output_dir,"vision.json"),"w",encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    except Exception as e:
        log("VISION", f"Failed: {e} — fallback.")
        return _fallback_extract(segments)


def _fallback_extract(segments):
    """Minimal fallback when Gemini fails — returns empty structure."""
    return {
        "main_topic": "",
        "core_conflict": "",
        "provocative_angle": "",
        "theme": "teaching",
        "festival": None,
        "location": None,
        "date": None
    }