import os, json, time
import httpx
import re
from .config import (
    get_glm_api_key,
    get_glm_base_url,
    get_glm_max_tokens,
    get_glm_model,
    get_mistral_api_key,
    is_glm_caption_eval_enabled,
)
from .runtime_config import is_economy_mode, is_quality_mode
from .utils import (
    log,
    PLATFORM_LIMITS,
    SHORT_MINIMUMS,
    REQUIRED_PLATFORMS,
    PLATFORMS,
    OPTIMAL_RANGES,
    track_api_call,
    track_api_success,
)

TAGS4 = "#KAILASA #Nithyananda"
TAGS3 = "#KAILASA #Nithyananda"
TAGS2 = "#KAILASA"
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

# Platform-specific caption overrides
PLATFORM_OVERRIDES = {
    "twitter": {"max_hashtags": 3, "hook_ratio": 0.35, "min_body": 30},
    "threads": {"max_hashtags": 3, "hook_ratio": 0.35, "min_body": 30},
    "instagram": {"hook_ratio": 0.45, "min_body": 50},
    "facebook": {"hook_ratio": 0.40, "min_body": 50, "paragraph_spacing": True},
    "tiktok": {"max_hashtags": 5, "hook_ratio": 0.40, "min_body": 30},
    "bluesky": {"max_hashtags": 3, "hook_ratio": 0.35, "min_body": 30},
    "youtube": {"hook_ratio": 0.40, "min_body": 80},
}

# Trim constants
SEPARATOR = "\n\n"
MIN_HOOK_CHARS = 50
MIN_BODY_THRESHOLD = 30

# Words to avoid ending on
STOP_WORDS = {
    "and",
    "but",
    "or",
    "the",
    "a",
    "an",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "dare",
    "ought",
    "used",
}

# Hashtag pattern - handles #AI-tools, #climate_change
HASHTAG_PATTERN = re.compile(r"#\w[\w\-]*")


def _get_platform_config(platform):
    return PLATFORM_OVERRIDES.get(
        platform, {"hook_ratio": 0.4, "min_body": MIN_BODY_THRESHOLD}
    )


def _language_meta(target_language):
    return LANGUAGE_META.get(
        target_language,
        {
            "name": str(target_language or "target language"),
            "style": f"Use natural devotional {target_language}.",
            "script_hint": f"Write in {target_language}.",
            "script_ranges": [],
        },
    )


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


def _build_prompt(
    main_topic,
    key_message,
    theme,
    transcript="",
    target_language="gu",
    target_platforms=None,
):
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
        if transcript
        else ""
    )
    return f"""SYSTEM: You are a devoted disciple of The Supreme Pontiff of Hinduism, Bhagavan Sri Nithyananda Paramashivam.
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
Topic: {main_topic or ""}
Key Message: {key_message or ""}
Theme: {theme or "teaching"}

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
"""


def _extract_str(val):
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        for k in ("caption", "text", "content"):
            v = val.get(k)
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                for k2 in ("caption", "text", "content"):
                    if isinstance(v.get(k2), str):
                        return v[k2]
    return str(val) if val else ""


def _normalize(raw):
    result = {}
    for p, data in raw.items():
        if isinstance(data, str):
            result[p] = {"caption": data}
        elif isinstance(data, dict):
            entry = {"caption": _extract_str(data.get("caption", data))}
            if p == "youtube":
                entry["title"] = _extract_str(data.get("title", ""))
            result[p] = entry
        else:
            result[p] = {"caption": str(data)}
    return result


def _validate_schema(captions, target_platforms=None):
    required = set(_normalize_target_platforms(target_platforms))
    missing = required - set(captions.keys())
    empty = [p for p in required if not captions.get(p, {}).get("caption", "").strip()]
    return missing, empty


def _smart_trim(text, limit, min_words=5):
    """Trim text to limit, preferring sentence/word boundaries.
    Avoids ending on stop words and ensures minimum word count.
    """
    if len(text) <= limit:
        return text

    t = text[:limit]

    # Try sentence boundary first
    for sep in [".", "!", "?", "\n"]:
        idx = t.rfind(sep)
        if idx > limit * 0.5:
            trimmed = t[: idx + 1].strip()
            # Check minimum words
            if len(trimmed.split()) >= min_words:
                # Avoid ending on stop words
                last_word = trimmed.split()[-1].lower().strip(".,!?")
                if last_word not in STOP_WORDS:
                    return trimmed

    # Try word boundary
    idx = t.rfind(" ")
    if idx > limit * 0.7:
        trimmed = t[:idx].strip()
        if len(trimmed.split()) >= min_words:
            last_word = trimmed.split()[-1].lower().strip(".,!?")
            if last_word not in STOP_WORDS:
                return trimmed + "..."

    # Last resort: hard cut, but try to avoid stop words
    words = t.split()
    while (
        words
        and words[-1].lower().strip(".,!?") in STOP_WORDS
        and len(" ".join(words)) > limit * 0.5
    ):
        words.pop()
    trimmed = " ".join(words)
    if trimmed and len(trimmed) < len(text):
        return trimmed.rstrip(".,!?") + "..."

    return t + "..."


def _effective_limit(platform):
    return SAFE_CAPTION_LIMITS.get(platform, PLATFORM_LIMITS.get(platform, 2000))


def _sanitize_caption_text(text, newline_before_tags=True):
    """Normalize generated caption text for publishing."""
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    # Remove stray leading/trailing quotes occasionally produced by LLM output.
    s = re.sub(r'^[\s"“”\'‘’`]+', "", s)
    s = re.sub(r'[\s"“”\'‘’`]+$', "", s)
    # Strip Markdown emphasis markers that should not appear in published captions.
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
    s = re.sub(r"__(.*?)__", r"\1", s)
    # Normalize markdown list bullets to platform-friendly bullet symbol.
    s = re.sub(r"(?m)^\s*[-*]\s+", f"{BULLET} ", s)
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


def _extract_trailing_hashtags(text):
    """Extract trailing hashtag block from caption.
    Handles: #AI #GovTech, #AI-tools, #climate_change, and mixed spacing.
    Detects: Lines with >=2 hashtags OR hashtag density>50%.
    """
    if not text:
        return text, ""

    lines = text.strip().split("\n")
    hashtag_block = []

    # Scan from end to find trailing hashtag block
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            if hashtag_block:
                break
            continue

        # Extract hashtags using regex (handles #-and underscores)
        hashtags_in_line = HASHTAG_PATTERN.findall(stripped)

        # Calculate hashtag density
        hashtag_chars = sum(len(h) for h in hashtags_in_line)
        non_hashtag_chars = len(re.sub(r"#\w[\w\-]*", "", stripped))

        # Check: >=2 hashtags OR hashtag density >50%
        if len(hashtags_in_line) >= 2 or (
            hashtag_chars > non_hashtag_chars and len(hashtags_in_line) > 0
        ):
            hashtag_block.insert(0, stripped)
        else:
            break

    if hashtag_block:
        body = "\n".join(
            lines[: -len(hashtag_block)] if len(hashtag_block) < len(lines) else lines
        )
        return body.strip(), "\n".join(hashtag_block)

    return text, ""


def _extract_cta_links(text):
    """Extract CTA phrases and URLs from caption."""
    if not text:
        return text, ""

    lines = text.strip().split("\n")
    cta_lines = []
    body_lines = []

    cta_keywords = [
        "link in bio",
        "watch the full",
        "subscribe",
        "learn more",
        "join us",
        "sign up",
        "full video",
        "click here",
        "follow us",
    ]

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        # URL detection
        if "http://" in lower or "https://" in lower or "www." in lower:
            cta_lines.append(stripped)
        # CTA phrase detection
        elif any(kw in lower for kw in cta_keywords):
            cta_lines.append(stripped)
        else:
            body_lines.append(stripped)

    return "\n".join(body_lines), "\n".join(cta_lines) if cta_lines else ""


def _split_hook_body(text, hook_limit=180):
    """Split caption into hook and body.
    hook_limit is adaptive - should be passed from parent based on available space.
    """
    if not text:
        return "", ""

    text = text.strip()
    if len(text) <= hook_limit:
        return text, ""

    # Try to end at sentence boundary within next 40 chars
    for i in range(hook_limit, min(hook_limit + 40, len(text))):
        if text[i] in ".!?" and (i + 1 >= len(text) or text[i + 1] in " \n"):
            return text[: i + 1].strip(), text[i + 1 :].strip()

    # Fallback: end at word boundary
    space_idx = text.rfind(" ", 0, hook_limit + 20)
    if space_idx > hook_limit * 0.5:  # More permissive for tight limits
        return text[:space_idx].strip(), text[space_idx:].strip()

    return text[:hook_limit].strip(), text[hook_limit:].strip()


def _priority_aware_trim(caption, max_chars, platform):
    """
    Trim caption preserving: hook, CTAs, hashtags.
    Uses intelligent degradation: body → hook → hashtags.
    All reserved space calculated BEFORE assembly.
    """
    if len(caption) <= max_chars:
        return caption

    # 1. Get platform config
    config = _get_platform_config(platform)
    max_hashtags = config.get("max_hashtags")
    min_body = config.get("min_body", MIN_BODY_THRESHOLD)
    hook_ratio = config.get("hook_ratio", 0.4)

    # 2. Extract preserved elements FIRST
    body_no_tags, hashtags = _extract_trailing_hashtags(caption)
    body_clean, cta_block = _extract_cta_links(body_no_tags)

    # 3. Apply hashtag limit per platform
    if max_hashtags and hashtags:
        hashtag_list = hashtags.split()
        if len(hashtag_list) > max_hashtags:
            hashtags = " ".join(hashtag_list[:max_hashtags])

    # 4. Calculate reserved space EXPLICITLY
    hashtag_len = len(hashtags)
    cta_len = len(cta_block)

    # Separators: hook\n\nbody\n\ncta\n\nhashtags
    # Max4 separators if all present
    separator_count = sum(1 for x in [True, body_clean, cta_block, hashtags] if x) - 1
    separator_count = max(0, separator_count)
    reserved = hashtag_len + cta_len + (separator_count * len(SEPARATOR))

    available = max_chars - reserved

    # 5. Determine hook limit with proper clamping
    if available < MIN_HOOK_CHARS:
        # Degenerate case: very tight space
        hook_limit = max(MIN_HOOK_CHARS // 2, int(available * 0.5))
    else:
        # Normal: adaptive hook with bounds
        hook_limit = max(
            MIN_HOOK_CHARS, min(int(available * hook_ratio), available - min_body)
        )

    # 6. Split hook from body with adaptive limit
    hook, body = _split_hook_body(body_clean, hook_limit)

    # 7. Calculate body space
    hook_len = len(hook) + (len(SEPARATOR) if hook else 0)
    body_available = max_chars - reserved - hook_len

    # 8. Trim body if needed
    if body and body_available > MIN_BODY_THRESHOLD:
        if len(body) > body_available:
            trimmed_body = _smart_trim(body, body_available)
        else:
            trimmed_body = body
    elif body_available > 0 and body:
        trimmed_body = _smart_trim(body, body_available)
    else:
        trimmed_body = ""

    # 9. Reassemble in priority order: hook + body + CTA + hashtags
    result_parts = []
    if hook:
        result_parts.append(hook)
    if trimmed_body:
        result_parts.append(trimmed_body)
    if cta_block:
        result_parts.append(cta_block)
    if hashtags:
        result_parts.append(hashtags)

    result = SEPARATOR.join(result_parts)

    # 10. Final degradation if still over limit
    if len(result) > max_chars and len(result_parts) > 1:
        # Stage 1: Trim body more aggressively
        if trimmed_body and len(trimmed_body) > 20:
            excess = len(result) - max_chars
            trimmed_body = _smart_trim(trimmed_body, len(trimmed_body) - excess)
            result_parts = [h for h in [hook, trimmed_body, cta_block, hashtags] if h]
            result = SEPARATOR.join(result_parts)

        # Stage 2: Reduce hook
        if len(result) > max_chars and len(hook) > MIN_HOOK_CHARS:
            hook = _smart_trim(hook, MIN_HOOK_CHARS)
            result_parts = [h for h in [hook, trimmed_body, cta_block, hashtags] if h]
            result = SEPARATOR.join(result_parts)

        # Stage 3: Reduce hashtags (platform-dependent)
        if len(result) > max_chars and hashtags:
            hashtag_list = hashtags.split()
            while len(result) > max_chars and len(hashtag_list) > 1:
                hashtag_list.pop()
                hashtags = " ".join(hashtag_list)
                result_parts = [
                    h for h in [hook, trimmed_body, cta_block, hashtags] if h
                ]
                result = SEPARATOR.join(result_parts)

    return result


def _call_mistral(api_key, prompt, max_retries=None, stats=None):
    """Use actual Mistral API instead of OpenRouter."""
    return _call_chat_provider(
        provider_name="mistral",
        api_key=api_key,
        prompt=prompt,
        url="https://api.mistral.ai/v1/chat/completions",
        model="mistral-large-latest",
        max_retries=max_retries,
        stats=stats,
    )


def _extract_chat_message_content(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _call_chat_provider(
    provider_name,
    api_key,
    prompt,
    url,
    model,
    max_retries=None,
    timeout=None,
    stats=None,
):
    if max_retries is None:
        max_retries = 1 if is_economy_mode() else 3
    max_tokens = 4096 if is_economy_mode() else 8192
    timeout = timeout or (75 if is_economy_mode() else 120)
    provider_label = str(provider_name or "provider").upper()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "top_p": 0.8,
        "max_tokens": max_tokens,
    }
    for attempt in range(1, max_retries + 1):
        if stats is not None:
            stats["api_calls"] = stats.get("api_calls", 0) + 1
        track_api_call(provider_name)
        started = time.perf_counter()
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 429:
                wait = 2**attempt  # exponential backoff: 2s, 4s, 8s
                if stats is not None:
                    stats["retries"] = stats.get("retries", 0) + 1
                log(
                    "CAPTION",
                    f"[{provider_label}] [RETRY] 429 — waiting {wait}s (attempt {attempt}/{max_retries})",
                )
                time.sleep(wait)
                continue
            r.raise_for_status()
            elapsed = round(time.perf_counter() - started, 3)
            if stats is not None:
                stats["latency_seconds"] = round(
                    stats.get("latency_seconds", 0.0) + elapsed, 3
                )
            track_api_success(provider_name)
            response_json = r.json()
            usage = response_json.get("usage", {})
            message = {}
            choices = response_json.get("choices") or []
            if choices:
                message = choices[0].get("message", {}) or {}
            content = _extract_chat_message_content(message.get("content"))
            if not content:
                raise RuntimeError(f"{provider_label} returned empty content.")
            log(
                "CAPTION",
                f"[{provider_label}] [SUCCESS] Tokens in:{usage.get('prompt_tokens', '?')} out:{usage.get('completion_tokens', '?')}",
            )
            return content
        except Exception as e:
            if stats is not None:
                stats.setdefault("errors", []).append(str(e))
            log("CAPTION", f"[{provider_label}] [FAIL] attempt {attempt}: {e}")
            if attempt == max_retries:
                raise
            wait = 2**attempt
            if stats is not None:
                stats["retries"] = stats.get("retries", 0) + 1
            log("CAPTION", f"[{provider_label}] [RETRY] waiting {wait}s before retry...")
            time.sleep(wait)
    raise RuntimeError(
        f"{provider_label} API failed after {max_retries} retries."
    )


def _call_glm(api_key, prompt, max_retries=None, stats=None):
    if max_retries is None:
        max_retries = 1 if is_economy_mode() else 3
    timeout = 75 if is_economy_mode() else 120
    provider_label = "GLM"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "prompt": prompt,
        "max_tokens": get_glm_max_tokens(),
        "model": get_glm_model(),
    }

    for attempt in range(1, max_retries + 1):
        if stats is not None:
            stats["api_calls"] = stats.get("api_calls", 0) + 1
        track_api_call("glm")
        started = time.perf_counter()
        try:
            r = httpx.post(
                get_glm_base_url(),
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            if r.status_code == 429:
                wait = 2**attempt
                if stats is not None:
                    stats["retries"] = stats.get("retries", 0) + 1
                log(
                    "CAPTION",
                    f"[{provider_label}] [RETRY] 429 — waiting {wait}s (attempt {attempt}/{max_retries})",
                )
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                body_preview = (r.text or "").strip()[:400]
                raise RuntimeError(
                    f"HTTP {r.status_code} from Modal GLM endpoint. Body: {body_preview or '<empty>'}"
                )
            r.raise_for_status()
            elapsed = round(time.perf_counter() - started, 3)
            if stats is not None:
                stats["latency_seconds"] = round(
                    stats.get("latency_seconds", 0.0) + elapsed, 3
                )
            track_api_success("glm")
            response_json = r.json()
            content = (
                response_json.get("text")
                or response_json.get("response")
                or response_json.get("completion")
                or response_json.get("output")
                or ""
            )
            if not content and isinstance(response_json.get("choices"), list):
                choices = response_json.get("choices") or []
                if choices:
                    message = choices[0].get("message", {}) or {}
                    content = _extract_chat_message_content(message.get("content"))
            content = _extract_chat_message_content(content)
            if not content:
                raise RuntimeError(
                    f"GLM returned empty content. Response keys: {sorted(response_json.keys())}"
                )
            log("CAPTION", f"[{provider_label}] [SUCCESS] Modal-native response received")
            return content
        except Exception as e:
            if stats is not None:
                stats.setdefault("errors", []).append(str(e))
            log("CAPTION", f"[{provider_label}] [FAIL] attempt {attempt}: {e}")
            if attempt == max_retries:
                raise
            wait = 2**attempt
            if stats is not None:
                stats["retries"] = stats.get("retries", 0) + 1
            log("CAPTION", f"[{provider_label}] [RETRY] waiting {wait}s before retry...")
            time.sleep(wait)
    raise RuntimeError(f"{provider_label} API failed after {max_retries} retries.")


def _provider_label(provider_name):
    return {
        "mistral": "Mistral Caption API",
        "glm": "GLM Caption API",
    }.get(str(provider_name or "").lower(), str(provider_name or "caption provider"))


def _provider_model(provider_name):
    provider_name = str(provider_name or "").lower()
    if provider_name == "mistral":
        return "mistral-large-latest"
    if provider_name == "glm":
        return get_glm_model()
    return ""


def _call_caption_provider(provider_name, api_key, prompt, stats=None):
    provider_name = str(provider_name or "").lower()
    if provider_name == "glm":
        return _call_glm(api_key, prompt, stats=stats)
    return _call_mistral(api_key, prompt, stats=stats)


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
    repaired = re.sub(r",(\s*[}\]])", r"\1", raw)
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
    required = {
        "youtube",
        "instagram",
        "tiktok",
        "facebook",
        "twitter",
        "threads",
        "bluesky",
    }

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
            log(
                "CAPTION",
                f"[VALIDATION_FAIL] Caption too long for {p}: {len(caption)} > {limit}",
            )
            return False, f"too_long:{p}"

    log("CAPTION", "[VALIDATION_PASS] All 7 platforms valid")
    return True, "ok"


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_provider_stats(provider_name):
    return {
        "provider": provider_name,
        "label": _provider_label(provider_name),
        "model": _provider_model(provider_name),
        "api_calls": 0,
        "retries": 0,
        "latency_seconds": 0.0,
        "errors": [],
        "warnings": [],
        "status": "pending",
    }


def _normalize_provider_output(captions, target_platforms):
    return {p: captions.get(p, {}) for p in target_platforms if p in captions}


def _run_caption_provider(
    provider_name,
    api_key,
    prompt,
    target_platforms,
    target_language,
):
    stats = _build_provider_stats(provider_name)
    captions = {}
    log("CAPTION", f"Calling {_provider_label(provider_name)} ...")
    raw = _call_caption_provider(provider_name, api_key, prompt, stats=stats)
    captions = _parse_raw(raw)
    captions = _normalize_provider_output(captions, target_platforms)

    missing, empty = _validate_schema(captions, target_platforms=target_platforms)
    if missing:
        stats["warnings"].append(f"missing:{','.join(sorted(missing))}")
        log("CAPTION", f"  WARNING: Missing platforms: {missing}")
    if empty:
        stats["warnings"].append(f"empty:{','.join(sorted(empty))}")
        log("CAPTION", f"  WARNING: Empty captions: {empty}")

    bad_script = [
        p
        for p, d in captions.items()
        if not _contains_target_script(d.get("caption", ""), target_language)
    ]
    if bad_script and _language_meta(target_language).get("script_ranges"):
        stats["warnings"].append(f"script:{','.join(sorted(bad_script))}")
        log(
            "CAPTION",
            f"  WARNING: Non-{_language_meta(target_language)['name']} output in {bad_script}",
        )

    bad_short = [
        p
        for p, mins in SHORT_MINIMUMS.items()
        if p in target_platforms
        if len(captions.get(p, {}).get("caption", "")) < mins
    ]
    if bad_short and is_quality_mode():
        log(
            "CAPTION",
            f"  Short captions on {bad_short} from {provider_name} — retrying ...",
        )
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
            raw2 = _call_caption_provider(provider_name, api_key, retry_prompt, stats=stats)
            captions2 = _parse_raw(raw2)
            for p in bad_short:
                new_len = len(captions2.get(p, {}).get("caption", ""))
                old_len = len(captions.get(p, {}).get("caption", ""))
                if new_len > old_len:
                    captions[p] = captions2.get(p, {})
        except Exception as e:
            stats["warnings"].append(f"short_retry_failed:{','.join(sorted(bad_short))}")
            log("CAPTION", f"Regeneration failed for {bad_short}: {e}")
    elif bad_short:
        stats["warnings"].append(f"short:{','.join(sorted(bad_short))}")
        log(
            "CAPTION",
            f"  Economy mode: accepting short captions for {bad_short} without regeneration.",
        )

    for p, data in captions.items():
        caption = data.get("caption", "")

        if p in ["instagram", "facebook", "youtube", "tiktok"]:
            missing_both = (
                "#kailasa" not in caption.lower()
                or "#nithyananda" not in caption.lower()
            )
            if missing_both and is_quality_mode():
                log("CAPTION", f"Missing required tags for {p} — regenerating...")
                try:
                    retry_prompt = (
                        f"{prompt}\n\nCRITICAL: The previous caption for {p} was missing required hashtags. "
                        f"Must include both #KAILASA and #Nithyananda hashtags. "
                        f"Regenerate the caption for {p} with proper hashtags. "
                        f"Return JSON ONLY for selected platforms: {', '.join(target_platforms)}."
                    )
                    raw_retry = _call_caption_provider(
                        provider_name, api_key, retry_prompt, stats=stats
                    )
                    new_captions = _parse_raw(raw_retry)
                    if new_captions.get(p) and new_captions[p].get("caption"):
                        captions[p] = new_captions[p]
                        caption = captions[p]["caption"]
                        log("CAPTION", f"Regenerated caption for {p}")
                except Exception as e:
                    stats["warnings"].append(f"tag_retry_failed:{p}")
                    log("CAPTION", f"Failed to regenerate {p}: {e}")
            elif missing_both:
                captions[p]["caption"] = _append_required_hashtags(p, caption)
                caption = captions[p]["caption"]
                log("CAPTION", f"Economy mode: appended required hashtags for {p}.")
        elif p in ["threads", "bluesky"]:
            missing_tag = "#kailasa" not in caption.lower()
            if missing_tag and is_quality_mode():
                log(
                    "CAPTION",
                    f"Missing required #KAILASA tag for {p} — regenerating...",
                )
                try:
                    retry_prompt = (
                        f"{prompt}\n\nCRITICAL: The previous caption for {p} was missing required #KAILASA hashtag. "
                        f"Must include #KAILASA hashtag. "
                        f"Regenerate the caption for {p} with proper hashtag. "
                        f"Return JSON ONLY for selected platforms: {', '.join(target_platforms)}."
                    )
                    raw_retry = _call_caption_provider(
                        provider_name, api_key, retry_prompt, stats=stats
                    )
                    new_captions = _parse_raw(raw_retry)
                    if new_captions.get(p) and new_captions[p].get("caption"):
                        captions[p] = new_captions[p]
                        caption = captions[p]["caption"]
                        log("CAPTION", f"Regenerated caption for {p}")
                except Exception as e:
                    stats["warnings"].append(f"kailasa_retry_failed:{p}")
                    log("CAPTION", f"Failed to regenerate {p}: {e}")
            elif missing_tag:
                captions[p]["caption"] = _append_required_hashtags(p, caption)
                caption = captions[p]["caption"]
                log("CAPTION", f"Economy mode: appended required hashtags for {p}.")

        if _language_meta(target_language).get("script_ranges") and p in [
            "instagram",
            "facebook",
            "youtube",
            "threads",
            "bluesky",
        ]:
            if (
                not _contains_target_script(caption, target_language)
                and is_quality_mode()
            ):
                log(
                    "CAPTION",
                    f"No {_language_meta(target_language)['name']} script detected in {p} caption — regenerating...",
                )
                try:
                    retry_prompt = (
                        f"{prompt}\n\nCRITICAL: The previous caption for {p} was not clearly written in {_language_meta(target_language)['name']}. "
                        f"Must be written in {_language_meta(target_language)['name']}. "
                        f"Regenerate the caption for {p} in proper {_language_meta(target_language)['name']}. "
                        f"Return JSON ONLY for selected platforms: {', '.join(target_platforms)}."
                    )
                    raw_retry = _call_caption_provider(
                        provider_name, api_key, retry_prompt, stats=stats
                    )
                    new_captions = _parse_raw(raw_retry)
                    if new_captions.get(p) and new_captions[p].get("caption"):
                        captions[p] = new_captions[p]
                        caption = captions[p]["caption"]
                        log("CAPTION", f"Regenerated caption for {p}")
                except Exception as e:
                    stats["warnings"].append(f"script_retry_failed:{p}")
                    log("CAPTION", f"Regeneration failed for {p}: {e}")

        hard_lim = PLATFORM_LIMITS.get(p, 2000)
        opt_range = OPTIMAL_RANGES.get(p)

        if len(caption) > hard_lim:
            stats["warnings"].append(f"too_long:{p}")
            log(
                "CAPTION",
                f"Caption exceeds hard limit for {p} ({len(caption)} > {hard_lim}) — keeping as-is",
            )

        if opt_range:
            opt_min, opt_max = opt_range
            if len(caption) < opt_min:
                stats["warnings"].append(f"below_optimal:{p}")
                log(
                    "CAPTION",
                    f"Caption short for {p} ({len(caption)} < {opt_min} optimal)",
                )
            elif len(caption) > opt_max:
                overage_pct = ((len(caption) - opt_max) / opt_max) * 100
                log(
                    "CAPTION",
                    f"Caption long for {p} ({len(caption)} > {opt_max} optimal, {overage_pct:.0f}% over)",
                )

                if overage_pct >= 30:
                    _, hashtags = _extract_trailing_hashtags(caption)
                    _, cta = _extract_cta_links(caption)
                    tag_count = (
                        len([w for w in hashtags.split() if w.startswith("#")])
                        if hashtags
                        else 0
                    )

                    trimmed = _priority_aware_trim(caption, opt_max, p)
                    min_len = SHORT_MINIMUMS.get(p, 80)
                    if len(trimmed) < min_len:
                        stats["warnings"].append(f"trim_aborted:{p}")
                        log(
                            "CAPTION",
                            f"  WARNING: Trimmed too short ({len(trimmed)} < {min_len}), keeping original",
                        )
                    else:
                        captions[p]["caption"] = trimmed
                        caption = trimmed
                        log(
                            "CAPTION",
                            f"→ Body trimmed (smart boundary) | Hashtags preserved ({tag_count} tags) | CTA preserved ({len(cta)} chars)",
                        )
                else:
                    log("CAPTION", "→ Within tolerance, keeping as-is")

    for p, data in captions.items():
        cleaned_caption = _sanitize_caption_text(
            _extract_str(data.get("caption", "")), newline_before_tags=True
        )
        data["caption"] = cleaned_caption
        if p == "youtube":
            title = _sanitize_caption_text(
                _extract_str(data.get("title", "")), newline_before_tags=False
            )
            data["title"] = title

    stats["status"] = "ok"
    return captions, stats


def _write_caption_files(output_dir, captions, target_platforms, basename="captions.json"):
    _save_json(os.path.join(output_dir, basename), captions)
    for p in target_platforms:
        data = captions.get(p, {})
        prefix = (
            f"TITLE: {data['title']}\n\n"
            if p == "youtube" and data.get("title")
            else ""
        )
        suffix = "" if basename == "captions.json" else f".{os.path.splitext(basename)[0]}"
        with open(
            os.path.join(output_dir, f"caption_{p}{suffix}.txt"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(prefix + data.get("caption", ""))


def _build_eval_summary(live_provider, live_captions, eval_provider, eval_captions, target_platforms):
    per_platform = {}
    for platform in target_platforms:
        live_entry = live_captions.get(platform, {})
        eval_entry = eval_captions.get(platform, {})
        live_caption = _extract_str(live_entry.get("caption", ""))
        eval_caption = _extract_str(eval_entry.get("caption", ""))
        item = {
            "live_length": len(live_caption),
            "eval_length": len(eval_caption),
            "captions_match": live_caption == eval_caption,
        }
        if platform == "youtube":
            item["live_title_length"] = len(_extract_str(live_entry.get("title", "")))
            item["eval_title_length"] = len(_extract_str(eval_entry.get("title", "")))
            item["titles_match"] = _extract_str(live_entry.get("title", "")) == _extract_str(
                eval_entry.get("title", "")
            )
        per_platform[platform] = item
    return {
        "live_provider": live_provider,
        "eval_provider": eval_provider,
        "platforms_compared": target_platforms,
        "per_platform": per_platform,
    }


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
        "live_provider": "mistral",
        "provider_stats": {},
        "evaluation": {
            "enabled": False,
            "provider": "glm",
            "status": "not_run",
            "files": [],
        },
    }
    main_topic = vision_data.get("main_topic", "")
    conflict = vision_data.get("core_conflict", "")
    prov = vision_data.get("provocative_angle", "")
    key_message = (conflict + " | " + prov).strip(" |")
    theme = vision_data.get("theme", "teaching")
    target_platforms = _normalize_target_platforms(selected_platforms)

    transcript_text = ""
    if segments:
        transcript_text = "\n".join(
            s.get("translated") or s.get("text", "") for s in segments
        ).strip()

    log("CAPTION", f"Vision -> topic: {main_topic[:60]}")
    log("CAPTION", f"Vision -> key_message: {key_message[:100]}")
    prompt = _build_prompt(
        main_topic,
        key_message,
        theme,
        transcript_text,
        target_language=target_language,
        target_platforms=target_platforms,
    )
    captions = {}
    mistral_key = get_mistral_api_key(api_key)
    glm_key = get_glm_api_key()
    glm_eval_enabled = is_glm_caption_eval_enabled()
    mode_name = "Economy" if is_economy_mode() else "Quality"
    log("CAPTION", f"Mode: {mode_name}")

    if mistral_key:
        try:
            captions, mistral_stats = _run_caption_provider(
                "mistral",
                mistral_key,
                prompt,
                target_platforms,
                target_language,
            )
            meta["provider_stats"]["mistral"] = mistral_stats
        except Exception as e:
            log("CAPTION", f"Error: {e} — fallback.")
            meta["used_fallback"] = True
            meta["reason"] = str(e)
            meta["provider_stats"]["mistral"] = {
                **_build_provider_stats("mistral"),
                "status": "error",
                "errors": [str(e)],
            }
            captions = _fallback_captions(
                vision_data,
                target_language=target_language,
                target_platforms=target_platforms,
            )
    else:
        log("CAPTION", "No key — fallback.")
        meta["used_fallback"] = True
        meta["reason"] = "No Mistral API key"
        meta["provider_stats"]["mistral"] = {
            **_build_provider_stats("mistral"),
            "status": "missing_key",
            "errors": ["No Mistral API key"],
        }
        captions = _fallback_captions(
            vision_data,
            target_language=target_language,
            target_platforms=target_platforms,
        )

    # Ensure we have captions (fallback if empty)
    if not captions:
        log("CAPTION", "Empty captions — using fallback.")
        meta["used_fallback"] = True
        if not meta.get("reason"):
            meta["reason"] = "Caption generation produced empty output"
        captions = _fallback_captions(
            vision_data,
            target_language=target_language,
            target_platforms=target_platforms,
        )

    captions = {p: captions.get(p, {}) for p in target_platforms if p in captions}
    missing_after_parse = [
        p
        for p in target_platforms
        if not captions.get(p, {}).get("caption", "").strip()
    ]
    if missing_after_parse:
        fallback_map = _fallback_captions(
            vision_data,
            target_language=target_language,
            target_platforms=target_platforms,
        )
        for p in missing_after_parse:
            captions[p] = fallback_map.get(p, {"caption": ""})

    for p, data in captions.items():
        cleaned_caption = _sanitize_caption_text(
            _extract_str(data.get("caption", "")), newline_before_tags=True
        )
        data["caption"] = cleaned_caption
        if p == "youtube":
            data["title"] = _sanitize_caption_text(
                _extract_str(data.get("title", "")), newline_before_tags=False
            )

    _write_caption_files(output_dir, captions, target_platforms, basename="captions.json")

    if glm_eval_enabled and mistral_key and not meta["used_fallback"]:
        meta["evaluation"]["enabled"] = True
        if glm_key:
            try:
                glm_captions, glm_stats = _run_caption_provider(
                    "glm",
                    glm_key,
                    prompt,
                    target_platforms,
                    target_language,
                )
                meta["provider_stats"]["glm"] = glm_stats
                summary = _build_eval_summary(
                    "mistral",
                    captions,
                    "glm",
                    glm_captions,
                    target_platforms,
                )
                mistral_file = os.path.join(output_dir, "captions_mistral_eval.json")
                glm_file = os.path.join(output_dir, "captions_glm_eval.json")
                summary_file = os.path.join(output_dir, "captions_eval_summary.json")
                meta_file = os.path.join(output_dir, "captions_provider_meta.json")
                _save_json(mistral_file, captions)
                _save_json(glm_file, glm_captions)
                _save_json(summary_file, summary)
                meta["evaluation"]["status"] = "ok"
                meta["evaluation"]["files"] = [
                    mistral_file,
                    glm_file,
                    summary_file,
                    meta_file,
                ]
                _save_json(meta_file, meta)
                log("CAPTION", "GLM caption evaluation artifacts saved.")
            except Exception as e:
                meta["provider_stats"]["glm"] = {
                    **_build_provider_stats("glm"),
                    "status": "error",
                    "errors": [str(e)],
                }
                meta["evaluation"]["status"] = "error"
                meta["evaluation"]["reason"] = str(e)
                meta_file = os.path.join(output_dir, "captions_provider_meta.json")
                meta["evaluation"]["files"] = [meta_file]
                _save_json(meta_file, meta)
                log("CAPTION", f"GLM caption evaluation failed: {e}")
        else:
            meta["evaluation"]["status"] = "missing_key"
            meta["evaluation"]["reason"] = "GLM_CAPTION_EVAL enabled but no GLM_API_KEY found"
            meta["provider_stats"]["glm"] = {
                **_build_provider_stats("glm"),
                "status": "missing_key",
                "errors": ["No GLM_API_KEY found"],
            }
            meta_file = os.path.join(output_dir, "captions_provider_meta.json")
            meta["evaluation"]["files"] = [meta_file]
            _save_json(meta_file, meta)
            log("CAPTION", "GLM caption evaluation skipped: no GLM API key.")
    elif glm_eval_enabled:
        meta["evaluation"]["enabled"] = True
        meta["evaluation"]["status"] = "skipped_live_provider_unavailable"
        meta["evaluation"]["reason"] = (
            "Mistral live captions were unavailable, so GLM side-by-side evaluation was skipped."
        )
        meta_file = os.path.join(output_dir, "captions_provider_meta.json")
        meta["evaluation"]["files"] = [meta_file]
        _save_json(meta_file, meta)
    else:
        meta_file = os.path.join(output_dir, "captions_provider_meta.json")
        _save_json(meta_file, meta)

    log("CAPTION", f"All captions saved ({len(target_platforms)} platforms).")
    return (captions, meta) if return_meta else captions


def _fallback_captions(vision_data, target_language="gu", target_platforms=None):
    topic = vision_data.get("main_topic", "") or ""
    conflict = vision_data.get("core_conflict", "") or ""
    prov = vision_data.get("provocative_angle", "") or ""
    hook = (prov or conflict or topic)[:120]
    body1 = (conflict or prov or topic)[:150]
    body2 = topic[:100] if topic and topic != body1 else ""
    bullets = BULLET + " " + body1
    if body2:
        bullets += "\n" + BULLET + " " + body2
    long_cap = hook + "\n\n" + bullets + "\n\n" + TAGS4
    all_caps = {
        "instagram": {"caption": long_cap},
        "facebook": {"caption": long_cap},
        "tiktok": {"caption": _smart_trim(hook + "\n\n#KAILASA #Nithyananda", 250)},
        "twitter": {
            "caption": _smart_trim(
                hook + " " + body1 + "\n\n#KAILASA #Nithyananda",
                100,
            )
        },
        "threads": {
            "caption": _smart_trim(hook + "\n\n" + body1 + "\n\n" + TAGS3, 250)
        },
        "bluesky": {
            "caption": _smart_trim(hook + "\n\n" + body1 + "\n\n" + TAGS2, 160)
        },
        "youtube": {
            "title": _smart_trim(topic or hook, 75),
            "caption": _smart_trim(long_cap, 4500),
        },
    }
    wanted = _normalize_target_platforms(target_platforms)
    result = {}
    for p in wanted:
        if p in all_caps:
            result[p] = all_caps[p]
        else:
            log("CAPTION", f"  WARNING: No fallback caption template for '{p}'")
    return result
