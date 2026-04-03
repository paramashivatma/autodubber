import os, json, time
import httpx
import re
from .config import get_mistral_api_key
from .runtime_config import is_economy_mode, is_quality_mode
from .utils import log, PLATFORM_LIMITS, SHORT_MINIMUMS, REQUIRED_PLATFORMS, PLATFORMS

TAGS4  = "#KAILASA #Nithyananda"
TAGS3  = "#KAILASA #Nithyananda"
TAGS2  = "#KAILASA"
BULLET = "•"

MAX_TRANSCRIPT_CHARS = 3000
SAFE_CAPTION_LIMITS = {
    "twitter": 250,
}

LANGUAGE_META = {
    "gu": {
        "name": "Gujarati",
        "style": "Use devotional Gujarati with natural Sanskrit terms where they fit.",
        "script_hint": "Write in Gujarati script.",
        "script_ranges": [(0x0A80, 0x0AFF)],
    },
    "hi": {
        "name": "Hindi",
        "style": "Use devotional Hindi with natural Sanskrit terms where they fit.",
        "script_hint": "Write in Devanagari script.",
        "script_ranges": [(0x0900, 0x097F)],
    },
    "ta": {
        "name": "Tamil",
        "style": "Use natural spoken Tamil with devotional warmth and Sanskrit terms only where they fit naturally.",
        "script_hint": "Write in Tamil script.",
        "script_ranges": [(0x0B80, 0x0BFF)],
    },
    "te": {
        "name": "Telugu",
        "style": "Use natural spoken Telugu with devotional warmth and Sanskrit terms only where they fit naturally.",
        "script_hint": "Write in Telugu script.",
        "script_ranges": [(0x0C00, 0x0C7F)],
    },
    "kn": {
        "name": "Kannada",
        "style": "Use natural spoken Kannada with devotional warmth and Sanskrit terms only where they fit naturally.",
        "script_hint": "Write in Kannada script.",
        "script_ranges": [(0x0C80, 0x0CFF)],
    },
    "ml": {
        "name": "Malayalam",
        "style": "Use natural spoken Malayalam with devotional warmth and Sanskrit terms only where they fit naturally.",
        "script_hint": "Write in Malayalam script.",
        "script_ranges": [(0x0D00, 0x0D7F)],
    },
    "bn": {
        "name": "Bengali",
        "style": "Use natural spoken Bengali with devotional warmth and Sanskrit terms only where they fit naturally.",
        "script_hint": "Write in Bengali script.",
        "script_ranges": [(0x0980, 0x09FF)],
    },
    "es": {
        "name": "Spanish",
        "style": "Use clear devotional Spanish that sounds natural to a native speaker.",
        "script_hint": "Write in Spanish.",
        "script_ranges": [],
    },
    "ru": {
        "name": "Russian",
        "style": "Use clear devotional Russian that sounds natural to a native speaker.",
        "script_hint": "Write in Cyrillic Russian.",
        "script_ranges": [(0x0400, 0x04FF)],
    },
    "en": {
        "name": "English",
        "style": "Use clear devotional English.",
        "script_hint": "Write in English.",
        "script_ranges": [],
    },
}

CAPTION_PLATFORM_ORDER = list(PLATFORMS)


def _language_meta(target_language):
    return LANGUAGE_META.get(target_language, {
        "name": str(target_language or "target language"),
        "style": f"Use natural devotional {target_language}.",
        "script_hint": f"Write in {target_language}.",
        "script_ranges": [],
    })


def _normalize_target_platforms(target_platforms=None):
    if not target_platforms:
        return list(CAPTION_PLATFORM_ORDER)
    selected = []
    allowed = set(CAPTION_PLATFORM_ORDER)
    for platform in target_platforms:
        key = str(platform or "").strip().lower()
        if key in allowed and key not in selected:
            selected.append(key)
    return selected or list(CAPTION_PLATFORM_ORDER)


def _build_prompt(main_topic, key_message, theme, transcript="", target_language="gu", target_platforms=None):
    meta = _language_meta(target_language)
    target_name = meta["name"]
    target_style = meta["style"]
    script_hint = meta["script_hint"]
    selected_platforms = _normalize_target_platforms(target_platforms)
    selected_keys = ", ".join(selected_platforms)
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "..."
        log("CAPTION", f"  Transcript capped at {MAX_TRANSCRIPT_CHARS} chars")
    transcript_block = (
        f"=== FULL TRANSCRIPT ({target_name}) ===\n{transcript}\n\n"
        if transcript else ""
    )
    return f'''SYSTEM: You are a devoted disciple of The Supreme Pontiff of Hinduism, Bhagavan Sri Nithyananda Paramashivam.
Your task is to craft social media captions that transmit sacred spiritual energy, reverence, and the transformative power of His teachings.
Speak as if guiding fellow disciples seeking inner awakening.
Write every caption in {target_name}. {target_style}
Each sentence should feel as if Guru's grace is flowing through it. Convey blessings, truths, and practices as experienced through the Guru's grace.
Do not invent ideas; remain fully faithful to the transcript.
{script_hint}
Generate captions ONLY for these platforms: {selected_keys}.
Adjust tone per platform:
- Instagram = punchy devotional energy, awakening curiosity.
- Facebook = nurturing reflection, guidance for inner peace.
- Threads/Bluesky = concise, spiritually resonant teaching.
- TikTok = energetic, recitable, spiritually uplifting.
- Twitter = declarative, Guru-guided statement.
- YouTube = detailed spiritual insights, structured for blessing, practice, transformation, and key teachings.

=== SOURCE ===
Topic: {main_topic or ''}
Key Message: {key_message or ''}
Theme: {theme or 'teaching'}

{transcript_block}=== PLATFORM BRIEFS ===

INSTAGRAM (max 1800 chars):
- Hook: one punchy devotional line directly quoting or paraphrasing from transcript, invoking inner awakening or Guru's blessing.
- 4 bullet points (•), each highlighting a blessing, a teaching, or a disciple practice from transcript. Each should connect to inner experience or practice.
- Generate 2-3 relevant devotional hashtags based on video content before the fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA #Nithyananda

FACEBOOK (max 1800 chars):
- Hook: speak directly to a disciple seeking peace, reflection, or devotion; different from Instagram. Should feel nurturing and contemplative.
- 4 bullet points (•), each highlighting a different blessing, teaching, or practice from transcript than Instagram bullets.
- Generate 2-3 relevant devotional hashtags based on video content before the fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA #Nithyananda

THREADS (max 350 chars including hashtags):
- Hook line from transcript; concise devotional tone.
- 2 complete sentences summarizing key teaching, blessing, or transformative practice for disciples.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA
- Minimum 200 chars. Maximum 350 chars. Count carefully.

TWITTER (target 180-240 chars; hard ceiling 250 including hashtags):
- Hook + one follow-up sentence. Both complete, declarative, and devotional, reflecting Guru's guidance and blessings.
- Prioritize conveying the spiritual essence concisely.
- End with: #KAILASA #Nithyananda
- Minimum 180 chars. Maximum 240 chars preferred. Never exceed 250 chars. Count carefully.

TIKTOK (max 180 chars including hashtags):
- ONE complete punchy devotional sentence directly from transcript; spiritually uplifting, recitable aloud, and energetic.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA #Nithyananda
- Minimum 80 chars. Maximum 180 chars. Count carefully.

BLUESKY (max 260 chars including hashtags):
- Hook sentence + one follow-up; both complete and devotional.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA
- Minimum 180 chars. Maximum 260 chars. Count carefully.

YOUTUBE (max 4500 chars):
- Hook line from transcript; devotional tone.
- 5 bullet points (•), structured as: 1) Blessing, 2) Practical disciple practice, 3) Transformation, 4-5) Key spiritual insights. Full sentences.
- Leave blank line between sections.
- Generate 2-3 relevant devotional hashtags based on video content before fixed tags.
- End with: [YOUR_GENERATED_HASHTAGS] #KAILASA #Nithyananda.
- Provide "title" field: max 75 chars, punchy devotional {target_name} title from transcript.

=== CRITICAL RULES ===
1. Every caption must be a COMPLETE thought; no mid-sentence cutoffs.
2. Instagram and Facebook hooks and bullets must be DIFFERENT in content and devotional angle.
3. All platforms with hashtags must end with proper punctuation before hashtags.
4. Respect minimum and maximum character limits on all platforms.
5. Zero English except fixed hashtags; maintain devotional {target_name} throughout.
6. Hashtags must be relevant to video content and spiritually aligned.
7. Twitter uses only fixed tags: #KAILASA #Nithyananda.
8. Each bullet or sentence must convey blessing, awakening, or sacred practice as per Guru's teaching.
9. Tone and energy should align with platform guidance as described above.
10. **CRITICAL: ALWAYS include required hashtags - NO EXCEPTIONS:**
   - Instagram, Facebook, YouTube, TikTok: MUST end with #KAILASA #Nithyananda
   - Threads, Bluesky: MUST end with #KAILASA
   - Failure to include required hashtags will cause regeneration

=== OUTPUT ===
Valid JSON only. No markdown fences. Output EXACTLY these keys only: {selected_keys}
Values: {{"caption": "...{target_name.lower()}..."}} — youtube also includes: {{"title": "...max 75 chars...", "caption": "..."}}
'''


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


def _validate_schema(captions, target_platforms=None):
    required = set(_normalize_target_platforms(target_platforms))
    missing = required - set(captions.keys())
    empty   = [p for p in required if not captions.get(p, {}).get("caption","").strip()]
    return missing, empty


def _smart_trim(text, limit):
    if len(text) <= limit: return text
    t = text[:limit]
    for sep in [".", "!", "?", "\n"]:
        idx = t.rfind(sep)
        if idx > limit * 0.5: return t[:idx+1].strip()
    idx = t.rfind(" ")
    return (t[:idx].strip() + "…") if idx > 0 else t + "…"


def _effective_limit(platform):
    return SAFE_CAPTION_LIMITS.get(platform, PLATFORM_LIMITS.get(platform, 2000))


def _sanitize_caption_text(text, newline_before_tags=True):
    """Normalize generated caption text for publishing."""
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    # Remove stray leading/trailing quotes occasionally produced by LLM output.
    s = re.sub(r'^[\s"“”\'‘’`]+', "", s)
    s = re.sub(r'[\s"“”\'‘’`]+$', "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)

    if newline_before_tags and "#" in s:
        tag_idx = s.find("#")
        if tag_idx > 0:
            head = s[:tag_idx].rstrip()
            tags = s[tag_idx:].lstrip()
            if head and not head.endswith("\n"):
                s = f"{head}\n\n{tags}"
            elif head:
                s = f"{head}\n{tags}"
            else:
                s = tags
    return s


def _append_required_hashtags(platform, caption):
    text = str(caption or "").strip()
    lower = text.lower()
    needed = []
    if platform in {"instagram", "facebook", "youtube", "tiktok", "twitter"}:
        if "#kailasa" not in lower:
            needed.append("#KAILASA")
        if "#nithyananda" not in lower:
            needed.append("#Nithyananda")
    elif platform in {"threads", "bluesky"}:
        if "#kailasa" not in lower:
            needed.append("#KAILASA")

    if not needed:
        return text
    sep = "\n\n" if text and "#" not in text else " "
    return (text + sep + " ".join(needed)).strip()


def _contains_target_script(text, target_language):
    if not text:
        return False
    ranges = _language_meta(target_language).get("script_ranges", [])
    if not ranges:
        return True
    total = len(text)
    hits = 0
    for c in text:
        code = ord(c)
        if any(start <= code <= end for start, end in ranges):
            hits += 1
    return (hits / max(total, 1)) > 0.2


def _call_mistral(api_key, prompt, max_retries=None):
    """Use actual Mistral API instead of OpenRouter."""
    if max_retries is None:
        max_retries = 1 if is_economy_mode() else 3
    max_tokens = 4096 if is_economy_mode() else 8192
    timeout = 75 if is_economy_mode() else 120
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
        "max_tokens": max_tokens,
    }
    for attempt in range(1, max_retries + 1):
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
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
        
        limit = _effective_limit(p)
        if len(caption) > limit:
            log("CAPTION", f"[VALIDATION_FAIL] Caption too long for {p}: {len(caption)} > {limit}")
            return False, f"too_long:{p}"
    
    log("CAPTION", "[VALIDATION_PASS] All 7 platforms valid")
    return True, "ok"


def generate_all_captions(
    vision_data,
    api_key=None,
    output_dir="workspace",
    segments=None,
    target_language="gu",
    return_meta=False,
    selected_platforms=None,
):
    os.makedirs(output_dir, exist_ok=True)
    meta = {
        "used_fallback": False,
        "reason": "",
        "provider": "mistral_caption",
    }
    main_topic  = vision_data.get("main_topic","")
    conflict    = vision_data.get("core_conflict","")
    prov        = vision_data.get("provocative_angle","")
    key_message = (conflict + " | " + prov).strip(" |")
    theme       = vision_data.get("theme","teaching")
    target_platforms = _normalize_target_platforms(selected_platforms)

    transcript_text = ""
    if segments:
        transcript_text = "\n".join(
            s.get("translated") or s.get("text", "") for s in segments
        ).strip()

    log("CAPTION", f"Vision -> topic: {main_topic[:60]}")
    log("CAPTION", f"Vision -> key_message: {key_message[:100]}")
    prompt      = _build_prompt(
        main_topic, key_message, theme, transcript_text,
        target_language=target_language,
        target_platforms=target_platforms,
    )
    captions    = {}
    mistral_key = get_mistral_api_key(api_key)
    mode_name = "Economy" if is_economy_mode() else "Quality"
    log("CAPTION", f"Mode: {mode_name}")

    if mistral_key:
        try:
            log("CAPTION", "Calling Mistral ...")
            raw      = _call_mistral(mistral_key, prompt)
            captions = _parse_raw(raw)
            captions = {p: captions.get(p, {}) for p in target_platforms if p in captions}

            # Schema validation
            missing, empty = _validate_schema(captions, target_platforms=target_platforms)
            if missing: log("CAPTION", f"  WARNING: Missing platforms: {missing}")
            if empty:   log("CAPTION", f"  WARNING: Empty captions: {empty}")

            # Target-language script check where detectable
            bad_script = [
                p for p, d in captions.items()
                if not _contains_target_script(d.get("caption", ""), target_language)
            ]
            if bad_script and _language_meta(target_language).get("script_ranges"):
                log("CAPTION", f"  WARNING: Non-{_language_meta(target_language)['name']} output in {bad_script}")

            # Short caption check + single retry
            bad_short = [p for p, mins in SHORT_MINIMUMS.items()
                         if p in target_platforms
                         if len(captions.get(p, {}).get("caption", "")) < mins]
            if bad_short and is_quality_mode():
                log("CAPTION", f"  Short captions on {bad_short} — retrying ...")
                twitter_instruction = ""
                if "twitter" in bad_short:
                    twitter_instruction = (
                        "For twitter specifically, keep the regenerated caption between 180 and 240 characters "
                        "and never exceed 250 characters including hashtags. "
                    )
                retry_prompt = (
                    f"{prompt}\n\nCRITICAL: Your previous output for {bad_short} was too short. "
                    f"Minimums: TikTok=80 chars, Twitter=180 chars, Threads=200 chars, Bluesky=180 chars. "
                    f"{twitter_instruction}"
                    f"Write LONGER complete sentences. Fill the limit without exceeding any platform max. "
                    f"Return JSON ONLY for selected platforms: {', '.join(target_platforms)}."
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
            elif bad_short:
                log("CAPTION", f"  Economy mode: accepting short captions for {bad_short} without regeneration.")
        
        except Exception as e:
            log("CAPTION", f"Error: {e} — fallback.")
            meta["used_fallback"] = True
            meta["reason"] = str(e)
            captions = _fallback_captions(
                vision_data, target_language=target_language, target_platforms=target_platforms
            )
    else:
        log("CAPTION", "No key — fallback.")
        meta["used_fallback"] = True
        meta["reason"] = "No Mistral API key"
        captions = _fallback_captions(
            vision_data, target_language=target_language, target_platforms=target_platforms
        )

    # Ensure we have captions (fallback if empty)
    if not captions:
        log("CAPTION", "Empty captions — using fallback.")
        meta["used_fallback"] = True
        if not meta.get("reason"):
            meta["reason"] = "Caption generation produced empty output"
        captions = _fallback_captions(
            vision_data, target_language=target_language, target_platforms=target_platforms
        )

    captions = {p: captions.get(p, {}) for p in target_platforms if p in captions}
    missing_after_parse = [p for p in target_platforms if not captions.get(p, {}).get("caption", "").strip()]
    if missing_after_parse:
        fallback_map = _fallback_captions(
            vision_data, target_language=target_language, target_platforms=target_platforms
        )
        for p in missing_after_parse:
            captions[p] = fallback_map.get(p, {"caption": ""})

    # Additional validation for required tags and character limits
    for p, data in captions.items():
        caption = data.get("caption", "")

        # Check for required hashtags per platform
        if p in ["instagram", "facebook", "youtube", "tiktok"]:
            # These platforms need both #KAILASA and #Nithyananda
            if ("#kailasa" not in caption.lower() or "#nithyananda" not in caption.lower()) and is_quality_mode():
                log("CAPTION",f"Missing required tags for {p} — regenerating...")
                try:
                    # Build regeneration prompt
                    retry_prompt = (
                        f"{prompt}\n\nCRITICAL: The previous caption for {p} was missing required hashtags. "
                        f"Must include both #KAILASA and #Nithyananda hashtags. "
                        f"Regenerate the caption for {p} with proper hashtags. "
                        f"Return JSON ONLY for selected platforms: {', '.join(target_platforms)}."
                    )
                    raw = _call_mistral(mistral_key, retry_prompt)
                    new_captions = _parse_raw(raw)
                    if new_captions.get(p) and new_captions[p].get("caption"):
                        captions[p] = new_captions[p]
                        log("CAPTION",f"Regenerated caption for {p}")
                except Exception as e:
                    log("CAPTION",f"Failed to regenerate {p}: {e}")
            elif "#kailasa" not in caption.lower() or "#nithyananda" not in caption.lower():
                captions[p]["caption"] = _append_required_hashtags(p, caption)
                caption = captions[p]["caption"]
                log("CAPTION", f"Economy mode: appended required hashtags for {p}.")
        elif p in ["threads", "bluesky"]:
            # These platforms only need #KAILASA
            if "#kailasa" not in caption.lower() and is_quality_mode():
                log("CAPTION",f"Missing required #KAILASA tag for {p} — regenerating...")
                try:
                    # Build regeneration prompt
                    retry_prompt = (
                        f"{prompt}\n\nCRITICAL: The previous caption for {p} was missing required #KAILASA hashtag. "
                        f"Must include #KAILASA hashtag. "
                        f"Regenerate the caption for {p} with proper hashtag. "
                        f"Return JSON ONLY for selected platforms: {', '.join(target_platforms)}."
                    )
                    raw = _call_mistral(mistral_key, retry_prompt)
                    new_captions = _parse_raw(raw)
                    if new_captions.get(p) and new_captions[p].get("caption"):
                        captions[p] = new_captions[p]
                        log("CAPTION",f"Regenerated caption for {p}")
                except Exception as e:
                    log("CAPTION",f"Failed to regenerate {p}: {e}")
            elif "#kailasa" not in caption.lower():
                captions[p]["caption"] = _append_required_hashtags(p, caption)
                caption = captions[p]["caption"]
                log("CAPTION", f"Economy mode: appended required hashtags for {p}.")

        # Check target-language script where detectable
        if _language_meta(target_language).get("script_ranges") and p in ["instagram", "facebook", "youtube", "threads", "bluesky"]:
            if not _contains_target_script(caption, target_language) and is_quality_mode():
                log("CAPTION",f"No {_language_meta(target_language)['name']} script detected in {p} caption — regenerating...")
                try:
                    retry_prompt = (
                        f"{prompt}\n\nCRITICAL: The previous caption for {p} was not clearly written in {_language_meta(target_language)['name']}. "
                        f"Must be written in {_language_meta(target_language)['name']}. "
                        f"Regenerate the caption for {p} in proper {_language_meta(target_language)['name']}. "
                        f"Return JSON ONLY for selected platforms: {', '.join(target_platforms)}."
                    )
                    raw = _call_mistral(mistral_key, retry_prompt)
                    new_captions = _parse_raw(raw)
                    if new_captions.get(p) and new_captions[p].get("caption"):
                        captions[p] = new_captions[p]
                        log("CAPTION",f"Regenerated caption for {p}")
                except Exception as e:
                    log("CAPTION",f"Regeneration failed for {p}: {e}")

        # Check character limits
        lim = _effective_limit(p)
        if len(caption) > lim:
            log("CAPTION",f"Caption too long for {p} ({len(caption)} > {lim}) — truncating...")
            captions[p]["caption"] = caption[:lim-1] + "…"
    
    for p, data in captions.items():
        lim = _effective_limit(p)
        cleaned_caption = _sanitize_caption_text(_extract_str(data.get("caption", "")), newline_before_tags=True)
        cleaned_caption = _smart_trim(cleaned_caption, lim)
        # One more pass after trim to remove any clipped quote artifacts.
        cleaned_caption = _sanitize_caption_text(cleaned_caption, newline_before_tags=True)
        if len(cleaned_caption) > lim:
            cleaned_caption = _smart_trim(cleaned_caption, lim)
        data["caption"] = cleaned_caption
        if p == "youtube":
            title = _sanitize_caption_text(_extract_str(data.get("title", "")), newline_before_tags=False)
            data["title"] = _smart_trim(title, 80)
    
    with open(os.path.join(output_dir,"captions.json"),"w",encoding="utf-8") as f:
        json.dump(captions, f, ensure_ascii=False, indent=2)
    for p in target_platforms:
        data = captions.get(p, {})
        prefix = f"TITLE: {data['title']}\n\n" if p=="youtube" and data.get("title") else ""
        with open(os.path.join(output_dir,f"caption_{p}.txt"),"w",encoding="utf-8") as f:
            f.write(prefix + data.get("caption",""))
    log("CAPTION", f"All captions saved ({len(target_platforms)} platforms).")
    return (captions, meta) if return_meta else captions

def _fallback_captions(vision_data, target_language="gu", target_platforms=None):
    topic    = vision_data.get("main_topic","") or ""
    conflict = vision_data.get("core_conflict","") or ""
    prov     = vision_data.get("provocative_angle","") or ""
    hook     = (prov or conflict or topic)[:120]
    body1    = (conflict or prov or topic)[:150]
    body2    = topic[:100] if topic and topic != body1 else ""
    bullets  = BULLET + " " + body1
    if body2:
        bullets += "\n" + BULLET + " " + body2
    long_cap = hook + "\n\n" + bullets + "\n\n" + TAGS4
    all_caps = {
        "instagram": {"caption": long_cap},
        "facebook":  {"caption": long_cap},
        "tiktok":    {"caption": _smart_trim(hook + "\n\n#KAILASA #Nithyananda", 180)},
        "twitter":   {"caption": _smart_trim(hook + " " + body1 + "\n\n#KAILASA #Nithyananda", _effective_limit("twitter"))},
        "threads":   {"caption": _smart_trim(hook + "\n\n" + body1 + "\n\n" + TAGS3, 350)},
        "bluesky":   {"caption": _smart_trim(hook + "\n\n" + body1 + "\n\n" + TAGS2, 260)},
        "youtube":   {"title": _smart_trim(topic or hook, 75), "caption": _smart_trim(long_cap, 4500)},
    }
    wanted = _normalize_target_platforms(target_platforms)
    return {p: all_caps[p] for p in wanted if p in all_caps}
