import os, json, time
import httpx
from dotenv import load_dotenv
from .utils import log, PLATFORM_LIMITS, SHORT_MINIMUMS, REQUIRED_PLATFORMS

load_dotenv()

TAGS4  = "#KAILASA #Nithyananda #સનાતનધર્મ #આધ્યાત્મ"
TAGS3  = "#KAILASA #Nithyananda #સનાતનધર્મ"
TAGS2  = "#KAILASA #આધ્યાત્મ"
BULLET = "•"

MAX_TRANSCRIPT_CHARS = 3000

CAPTION_PROMPT_TEMPLATE = """\
SYSTEM: You are a devoted disciple of The Supreme Pontiff of Hinduism, Bhagavan Sri Nithyananda Paramashivam. 
Your task is to craft social media captions that transmit sacred spiritual energy, reverence, and the transformative power of His teachings. 
Speak as if guiding fellow disciples seeking inner awakening, using devotional Gujarati and appropriate Sanskrit terms naturally. 
Each sentence should feel as if Guru's grace is flowing through it. Convey blessings, truths, and practices as experienced through the Guru's grace. 
Do not invent ideas; remain fully faithful to the transcript. 
Adjust tone per platform:
- Instagram = punchy devotional energy, awakening curiosity.
- Facebook = nurturing reflection, guidance for inner peace.
- Threads/Bluesky = concise, spiritually resonant teaching.
- TikTok = energetic, recitable, spiritually uplifting.
- Twitter = declarative, Guru-guided statement.
- YouTube = detailed spiritual insights, structured for blessing, practice, transformation, and key teachings.

=== SOURCE ===
Topic: MAIN_TOPIC_HERE
Key Message: KEY_MESSAGE_HERE
Theme: THEME_HERE

TRANSCRIPT_BLOCK_HERE
=== PLATFORM BRIEFS ===

INSTAGRAM (max 1800 chars):
- Hook: one punchy devotional line directly quoting or paraphrasing from transcript, invoking inner awakening or Guru's blessing.
- 4 bullet points (•), each highlighting a blessing, a teaching, or a disciple practice from transcript. Each should connect to inner experience or practice.
- Generate 2-3 relevant devotional hashtags based on video content (Sanskritized Gujarati encouraged) before the fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA #Nithyananda

FACEBOOK (max 1800 chars):
- Hook: speak directly to a disciple seeking peace, reflection, or devotion; different from Instagram. Should feel nurturing and contemplative.
- 4 bullet points (•), each highlighting a different blessing, teaching, or practice from transcript than Instagram bullets. Connect to inner reflection or meditation practice.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA #Nithyananda

THREADS (max 350 chars including hashtags):
- Hook line from transcript; concise devotional tone.
- 2 complete sentences summarizing key teaching, blessing, or transformative practice for disciples.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA
- Use Sanskritized Gujarati words naturally for spiritual resonance.
- Minimum 200 chars. Maximum 350 chars. Count carefully.

TWITTER (max 260 chars including hashtags):
- Hook + one follow-up sentence. Both complete, declarative, and devotional, reflecting Guru's guidance and blessings.
- Prioritize conveying the spiritual essence concisely.
- End with: #KAILASA #Nithyananda
- Minimum 180 chars. Maximum 260 chars. Count carefully.

TIKTOK (max 180 chars including hashtags):
- ONE complete punchy devotional sentence directly from transcript; spiritually uplifting, recitable aloud, and energetic.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA #Nithyananda
- Minimum 80 chars. Maximum 180 chars. Count carefully.

BLUESKY (max 260 chars including hashtags):
- Hook sentence + one follow-up; both complete and devotional.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA
- Use concise Sanskritized Gujarati terms where they naturally convey the teaching.
- Minimum 180 chars. Maximum 260 chars. Count carefully.

YOUTUBE (max 4500 chars):
- Hook line from transcript; devotional tone.
- 5 bullet points (•), structured as: 1) Blessing, 2) Practical disciple practice, 3) Transformation, 4–5) Key spiritual insights. Full sentences.
- Leave blank line between sections.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA #Nithyananda
- Provide "title" field: max 75 chars, punchy devotional Gujarati title from transcript.

=== CRITICAL RULES ===
1. Every caption must be a COMPLETE thought; no mid-sentence cutoffs.
2. Instagram and Facebook hooks and bullets must be DIFFERENT in content and devotional angle.
3. All platforms with hashtags must end with proper punctuation before hashtags.
4. Respect minimum and maximum character limits on all platforms.
5. Zero English; maintain devotional Gujarati throughout.
6. Hashtags must be relevant to video content and spiritually aligned.
7. Twitter uses only fixed tags: #KAILASA #Nithyananda.
8. Each bullet or sentence must convey blessing, awakening, or sacred practice as per Guru's teaching.
9. Encourage Sanskritized Gujarati words naturally for spiritual resonance.
10. Tone and energy should align with platform guidance as described above.

=== OUTPUT ===
Valid JSON only. No markdown fences. Exactly 7 keys: instagram, facebook, tiktok, twitter, youtube, threads, bluesky
Values: {"caption": "...gujarati..."} — youtube also includes: {"title": "...max 75 chars...", "caption": "..."}
"""


def _build_prompt(main_topic, key_message, theme, transcript=""):
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "..."
        log("CAPTION", f"  Transcript capped at {MAX_TRANSCRIPT_CHARS} chars")
    transcript_block = (
        f"=== FULL TRANSCRIPT (Gujarati) ===\n{transcript}\n\n"
        if transcript else ""
    )
    return (CAPTION_PROMPT_TEMPLATE
            .replace("MAIN_TOPIC_HERE",  main_topic  or "")
            .replace("KEY_MESSAGE_HERE", key_message or "")
            .replace("THEME_HERE",       theme       or "teaching")
            .replace("TRANSCRIPT_BLOCK_HERE", transcript_block))


def _extract_str(val):
    if isinstance(val, str): return val
    if isinstance(val, dict):
        for k in ("caption","text","content"):
            v = val.get(k)
            if isinstance(v, str): return v
            if isinstance(v, dict):
                for k2 in ("caption","text","content"):
                    if isinstance(v.get(k2), str): return v[k2]
    return str(val) if val else ""


def _normalize(raw):
    result = {}
    for p, data in raw.items():
        if isinstance(data, str): result[p] = {"caption": data}
        elif isinstance(data, dict):
            entry = {"caption": _extract_str(data.get("caption", data))}
            if p == "youtube": entry["title"] = _extract_str(data.get("title",""))
            result[p] = entry
        else: result[p] = {"caption": str(data)}
    return result


def _validate_schema(captions):
    missing = REQUIRED_PLATFORMS - set(captions.keys())
    empty   = [p for p in REQUIRED_PLATFORMS if not captions.get(p, {}).get("caption","").strip()]
    return missing, empty


def _smart_trim(text, limit):
    if len(text) <= limit: return text
    t = text[:limit]
    for sep in [".", "!", "?", "\n"]:
        idx = t.rfind(sep)
        if idx > limit * 0.5: return t[:idx+1].strip()
    idx = t.rfind(" ")
    return (t[:idx].strip() + "…") if idx > 0 else t + "…"


def _is_gujarati(text):
    if not text: return False
    return sum(1 for c in text if "\u0a80" <= c <= "\u0aff") / len(text) > 0.6


def _call_mistral(api_key, prompt, max_retries=3):
    """Use actual Mistral API instead of OpenRouter."""
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "model": "mistral-large-latest",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "top_p": 0.8,
        "max_tokens": 8192,
    }
    for attempt in range(1, max_retries + 1):
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=120)
            if r.status_code == 429:
                wait = 2 ** attempt  # exponential backoff: 2s, 4s, 8s
                log("CAPTION", f"[RETRY] 429 — waiting {wait}s (attempt {attempt}/{max_retries})")
                time.sleep(wait)
                continue
            r.raise_for_status()
            response_json = r.json()
            usage = response_json.get("usage", {})
            log("CAPTION", f"[SUCCESS] Tokens in:{usage.get('prompt_tokens','?')} out:{usage.get('completion_tokens','?')}")
            return response_json["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log("CAPTION", f"[FAIL] attempt {attempt}: {e}")
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            log("CAPTION", f"[RETRY] waiting {wait}s before retry...")
            time.sleep(wait)
    raise RuntimeError(f"Mistral API failed after {max_retries} retries.")


def _parse_raw(raw):
    """Parse JSON from LLM response with repair layer and retries."""
    import re
    
    def _try_parse(text):
        """Try to parse JSON with various repair strategies."""
        # Strategy 1: Extract from markdown code fences
        if "```" in text:
            pattern = r"```(?:json)?\s*(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                text = matches[-1].strip()
        
        # Strategy 2: Find JSON object pattern
        try:
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
            return _normalize(json.loads(text.strip()))
        except json.JSONDecodeError:
            return None
    
    # Try parsing original
    result = _try_parse(raw)
    if result:
        return result
    
    # Try repairing common issues
    log("CAPTION", "[JSON_REPAIR] Initial parse failed, attempting repair...")
    
    # Repair: Fix trailing commas
    repaired = re.sub(r',(\s*[}\]])', r'\1', raw)
    result = _try_parse(repaired)
    if result:
        log("CAPTION", "[JSON_REPAIR] Fixed trailing commas")
        return result
    
    # Repair: Fix unescaped quotes in strings (basic)
    repaired = re.sub(r'("[^"]*)(?<!\\)"([^"]*")', r'\1\\"\2', raw)
    result = _try_parse(repaired)
    if result:
        log("CAPTION", "[JSON_REPAIR] Fixed unescaped quotes")
        return result
    
    log("CAPTION", "[FAIL] JSON repair failed — returning empty dict")
    return {}


def _strict_validate(captions):
    """Strict validation: ensure all 7 platforms exist, non-empty, within limits."""
    required = {"youtube", "instagram", "tiktok", "facebook", "twitter", "threads", "bluesky"}
    
    # Check all platforms present
    missing = required - set(captions.keys())
    if missing:
        log("CAPTION", f"[VALIDATION_FAIL] Missing platforms: {missing}")
        return False, f"missing:{missing}"
    
    # Check non-empty and within limits
    for p in required:
        data = captions.get(p, {})
        caption = data.get("caption", "").strip()
        
        if not caption:
            log("CAPTION", f"[VALIDATION_FAIL] Empty caption for {p}")
            return False, f"empty:{p}"
        
        limit = PLATFORM_LIMITS.get(p, 2000)
        if len(caption) > limit:
            log("CAPTION", f"[VALIDATION_FAIL] Caption too long for {p}: {len(caption)} > {limit}")
            return False, f"too_long:{p}"
    
    log("CAPTION", "[VALIDATION_PASS] All 7 platforms valid")
    return True, "ok"


def generate_all_captions(vision_data, api_key=None, output_dir="workspace", segments=None):
    os.makedirs(output_dir, exist_ok=True)
    main_topic  = vision_data.get("main_topic","")
    conflict    = vision_data.get("core_conflict","")
    prov        = vision_data.get("provocative_angle","")
    key_message = (conflict + " | " + prov).strip(" |")
    theme       = vision_data.get("theme","teaching")

    transcript_text = ""
    if segments:
        transcript_text = "\n".join(
            s.get("translated") or s.get("text", "") for s in segments
        ).strip()

    log("CAPTION", f"Vision -> topic: {main_topic[:60]}")
    log("CAPTION", f"Vision -> key_message: {key_message[:100]}")
    prompt      = _build_prompt(main_topic, key_message, theme, transcript_text)
    captions    = {}
    mistral_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("MISTRAL_API_KEY") or "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"

    if mistral_key:
        try:
            log("CAPTION", "Calling Mistral ...")
            raw      = _call_mistral(mistral_key, prompt)
            captions = _parse_raw(raw)

            # Schema validation
            missing, empty = _validate_schema(captions)
            if missing: log("CAPTION", f"  WARNING: Missing platforms: {missing}")
            if empty:   log("CAPTION", f"  WARNING: Empty captions: {empty}")

            # Gujarati script check
            bad_script = [p for p, d in captions.items() if not _is_gujarati(d.get("caption",""))]
            if bad_script:
                log("CAPTION", f"  WARNING: Non-Gujarati output in {bad_script}")

            # Short caption check + single retry
            bad_short = [p for p, mins in SHORT_MINIMUMS.items()
                         if len(captions.get(p, {}).get("caption", "")) < mins]
            if bad_short:
                log("CAPTION", f"  Short captions on {bad_short} — retrying ...")
                retry_prompt = (
                    f"{prompt}\n\nCRITICAL: Your previous output for {bad_short} was too short. "
                    f"Minimums: TikTok=80 chars, Twitter=180 chars, Threads=200 chars, Bluesky=180 chars. "
                    f"Write LONGER complete sentences. Fill the limit. Return full JSON for all 7 platforms."
                )
                try:
                    raw2      = _call_mistral(mistral_key, retry_prompt)
                    captions2 = _parse_raw(raw2)
                    for p in bad_short:
                        new_len = len(captions2.get(p, {}).get("caption", ""))
                        old_len = len(captions.get(p, {}).get("caption", ""))
                        if new_len > old_len:
                            captions[p] = captions2.get(p, {})
                except Exception as e:
                    log("CAPTION",f"Regeneration failed for {p}: {e}")
        
        except Exception as e:
            log("CAPTION", f"Error: {e} — fallback.")
            captions = _fallback_captions(vision_data)
    else:
        log("CAPTION", "No key — fallback.")
        captions = _fallback_captions(vision_data)

    # Ensure we have captions (fallback if empty)
    if not captions:
        log("CAPTION", "Empty captions — using fallback.")
        captions = _fallback_captions(vision_data)

    # Additional validation for required tags and character limits
    for p, data in captions.items():
        caption = data.get("caption", "")

        # Check for required hashtags
        if p in ["instagram", "facebook", "youtube", "threads", "bluesky", "tiktok"]:
            if "#kailasa" not in caption.lower() or "#nithyananda" not in caption.lower():
                log("CAPTION",f"Missing required tags for {p} — regenerating...")
                try:
                    new_captions = _call_mistral(vision_data, mistral_key)
                    if new_captions.get(p) and new_captions[p].get("caption"):
                        captions[p] = new_captions[p]
                        log("CAPTION",f"Regenerated caption for {p}")
                except Exception as e:
                    log("CAPTION",f"Regeneration failed for {p}: {e}")

        # Check Gujarati content for Gujarati platforms
        if p in ["instagram", "facebook", "youtube", "threads", "bluesky"]:
            if not _contains_gujarati(caption):
                log("CAPTION",f"No Gujarati characters in {p} caption — regenerating...")
                try:
                    new_captions = _call_mistral(vision_data, mistral_key)
                    if new_captions.get(p) and new_captions[p].get("caption"):
                        captions[p] = new_captions[p]
                        log("CAPTION",f"Regenerated caption for {p}")
                except Exception as e:
                    log("CAPTION",f"Regeneration failed for {p}: {e}")

        # Check character limits
        lim = PLATFORM_LIMITS.get(p, 2000)
        if len(caption) > lim:
            log("CAPTION",f"Caption too long for {p} ({len(caption)} > {lim}) — truncating...")
            captions[p]["caption"] = caption[:lim-1] + "…"
    
    for p, data in captions.items():
        lim = PLATFORM_LIMITS.get(p, 2000)
        data["caption"] = _smart_trim(_extract_str(data.get("caption","")), lim)
        if p == "youtube":
            data["title"] = _smart_trim(_extract_str(data.get("title","")), 80)
    
    with open(os.path.join(output_dir,"captions.json"),"w",encoding="utf-8") as f:
        json.dump(captions, f, ensure_ascii=False, indent=2)
    for p, data in captions.items():
        prefix = f"TITLE: {data['title']}\n\n" if p=="youtube" and data.get("title") else ""
        with open(os.path.join(output_dir,f"caption_{p}.txt"),"w",encoding="utf-8") as f:
            f.write(prefix + data.get("caption",""))
    log("CAPTION","All captions saved.")
    return captions

def _contains_gujarati(text):
    """Check if text contains Gujarati characters"""
    gujarati_range = range(0x0A80, 0x0AFF + 1)
    return any(ord(char) in gujarati_range for char in text)

def _fallback_captions(vision_data):
    topic    = vision_data.get("main_topic","") or ""
    conflict = vision_data.get("core_conflict","") or ""
    prov     = vision_data.get("provocative_angle","") or ""
    hook     = (prov or conflict or topic)[:120]
    body1    = (conflict or prov or topic)[:150]
    body2    = topic[:100] if topic and topic != body1 else ""
    bullets  = BULLET + " " + body1
    if body2: bullets += "\n" + BULLET + " " + body2
    long_cap = hook + "\n\n" + bullets + "\n\n" + TAGS4
    return {
        "instagram": {"caption": long_cap},
        "facebook":  {"caption": long_cap},
        "tiktok":    {"caption": _smart_trim(hook, 160)},
        "twitter":   {"caption": _smart_trim(hook + " " + body1, 240)},
        "threads":   {"caption": _smart_trim(hook + "\n\n" + body1 + "\n\n" + TAGS3, 350)},
        "bluesky":   {"caption": _smart_trim(hook + "\n\n" + TAGS2, 260)},
        "youtube":   {"title": _smart_trim(topic or hook, 75), "caption": long_cap},
    }