import os, json, time
from .utils import log
from .runtime_config import is_economy_mode
from .config import get_gemini_api_key

GUJARATI_RANGE = (0x0A80, 0x0AFF)

NON_GUJARATI_SCRIPTS = [
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0900, 0x097F),  # Devanagari
    (0x0980, 0x09FF),  # Bengali
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
]

# Translation cache
_cache_file = "translation_cache.json"
_translation_cache = {}

# Runtime state for a single translate_segments invocation.
_gemini_quota_exhausted = False
_gemini_quota_reason = ""
_gemini_skip_logged = False
_last_runtime_meta = {
    "used_fallback": False,
    "reason": "",
}


def _reset_runtime_state():
    global \
        _gemini_quota_exhausted, \
        _gemini_quota_reason, \
        _gemini_skip_logged, \
        _last_runtime_meta
    _gemini_quota_exhausted = False
    _gemini_quota_reason = ""
    _gemini_skip_logged = False
    _last_runtime_meta = {"used_fallback": False, "reason": ""}


def get_translation_runtime_meta():
    """Return metadata from the latest translate_segments run."""
    return dict(_last_runtime_meta)


def _is_quota_exhausted_error(err_text):
    s = str(err_text or "").lower()
    # Daily free-tier exhaustion patterns from Gemini responses.
    quota_tokens = (
        "resource_exhausted",
        "quota exceeded",
        "free_tier_requests",
        "generaterequestsperday",
        "perdayperproject",
        "limit: 20",
    )
    return any(t in s for t in quota_tokens)


def _mark_quota_exhausted(reason):
    global _gemini_quota_exhausted, _gemini_quota_reason
    if not _gemini_quota_exhausted:
        _gemini_quota_exhausted = True
        _gemini_quota_reason = str(reason or "")
        log(
            "TRANSLATE",
            "  Gemini quota exhausted. Switching to Google Translate fallback for remaining segments in this run.",
        )


def _log_skip_once():
    global _gemini_skip_logged
    if _gemini_quota_exhausted and not _gemini_skip_logged:
        _gemini_skip_logged = True
        reason = _gemini_quota_reason or "quota exhausted"
        log(
            "TRANSLATE",
            f"  Gemini disabled for this run ({reason}); skipping further Gemini calls.",
        )


def _google_translate_text(text, target_language, source_hint="auto", use_pivot=True):
    """Google Translate helper with optional English pivot for Gujarati quality."""
    from deep_translator import GoogleTranslator

    direct = GoogleTranslator(source="auto", target=target_language).translate(text)
    if target_language != "gu":
        return direct

    if direct and _is_gujarati_script(direct) and not _has_foreign_script(direct):
        return direct

    if use_pivot and source_hint != "en":
        try:
            english = GoogleTranslator(source="auto", target="en").translate(text)
            pivoted = GoogleTranslator(source="en", target="gu").translate(english)
            if pivoted:
                return pivoted
        except Exception as e:
            log("TRANSLATE", f"  Pivot error: {e}")
    return direct


def _load_cache():
    """Load translation cache from file."""
    global _translation_cache
    if os.path.exists(_cache_file):
        try:
            with open(_cache_file, "r", encoding="utf-8") as f:
                _translation_cache = json.load(f)
            log("TRANSLATE", f"[CACHE] Loaded {len(_translation_cache)} entries")
        except Exception as e:
            log("TRANSLATE", f"[CACHE] Load failed: {e}")
            _translation_cache = {}
    else:
        _translation_cache = {}


def _save_cache():
    """Save translation cache to file."""
    try:
        with open(_cache_file, "w", encoding="utf-8") as f:
            json.dump(_translation_cache, f, ensure_ascii=False, indent=2)
        log("TRANSLATE", f"[CACHE] Saved {len(_translation_cache)} entries")
    except Exception as e:
        log("TRANSLATE", f"[CACHE] Save failed: {e}")


def _normalize_key(text, target_language="gu"):
    """Normalize text for cache key, scoped by target language."""
    return f"{target_language}::{text.strip().lower()}"


def _get_cached(text, target_language="gu"):
    """Get cached translation if exists."""
    key = _normalize_key(text, target_language)
    return _translation_cache.get(key)


def _set_cached(text, translation, target_language="gu"):
    """Cache translation if text is short enough."""
    if len(text) < 300:
        key = _normalize_key(text, target_language)
        _translation_cache[key] = translation


# Load cache on module import
_load_cache()


def _is_gujarati_script(text):
    if not text:
        return False
    guj_chars = sum(1 for c in text if GUJARATI_RANGE[0] <= ord(c) <= GUJARATI_RANGE[1])
    return guj_chars / len(text) > 0.25


def _has_foreign_script(text):
    if not text:
        return False
    for start, end in NON_GUJARATI_SCRIPTS:
        foreign = sum(1 for c in text if start <= ord(c) <= end)
        if foreign / len(text) > 0.10:
            return True
    return False


def _gemini_translate(text, source_hint="auto", target_language="gu"):
    from google import genai
    from google.genai import types

    if _gemini_quota_exhausted:
        raise RuntimeError(
            f"Gemini disabled for this run: {_gemini_quota_reason or 'quota exhausted'}"
        )

    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("No Gemini API key found.")

    client = genai.Client(api_key=api_key)

    lang_names = {
        "gu": "Gujarati",
        "hi": "Hindi",
        "ta": "Tamil",
        "te": "Telugu",
        "kn": "Kannada",
        "ml": "Malayalam",
        "bn": "Bengali",
        "es": "Spanish",
        "ru": "Russian",
        "en": "English",
        "auto": "the detected language",
    }

    source_lang = lang_names.get(source_hint, source_hint)
    target_lang = lang_names.get(target_language, target_language)

    prompt = f"""Translate the following text from {source_lang} to {target_lang}.

Context: This is a spiritual/Vedantic teaching by a Hindu monk about Hindu deities, traditions, and sacred places.

RULES:
1. PROPER NOUNS: If a name seems clearly misheard (e.g., "Allama" in a Tamil spiritual context likely means "ella malla"), correct it. Otherwise, transliterate names as-is.
2. REVERENCE: Maintain a respectful, devotional tone. Keep sacred terms (e.g., Bhakti, Dharma, Prasad) in their original form if natural in {target_lang}.
3. TTS OPTIMIZED: Use clear punctuation for natural pauses (commas for breaths, periods for full stops). Avoid symbols like *, _, (), or brackets.
4. NATURAL SPEECH: Write for the ear, not the eye. Use conversational {target_lang}, not literary or formal style.

Return ONLY the translation. No explanations.

Text to translate:
{text}"""

    max_attempts = 1 if is_economy_mode() else 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    top_p=0.8,
                    max_output_tokens=1024,
                ),
            )
            result = response.text.strip()
            if result:
                return result
        except Exception as e:
            log("TRANSLATE", f"  Gemini attempt {attempt} failed: {e}")
            if _is_quota_exhausted_error(e):
                _mark_quota_exhausted(e)
                raise RuntimeError(f"Gemini quota exhausted: {e}")
            if attempt == max_attempts:
                raise RuntimeError(
                    f"Gemini translation failed after {max_attempts} attempts: {e}"
                )
            time.sleep((1 if is_economy_mode() else 3) * attempt)

    raise RuntimeError(f"Gemini translation failed after {max_attempts} attempts.")


def _gemini_translate_batch(texts, source_hint, target_language):
    """Translate multiple texts in a single Gemini API call"""
    from google import genai
    from google.genai import types

    if _gemini_quota_exhausted:
        raise RuntimeError(
            f"Gemini disabled for this run: {_gemini_quota_reason or 'quota exhausted'}"
        )

    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("No Gemini API key found.")

    client = genai.Client(api_key=api_key)

    lang_names = {
        "gu": "Gujarati",
        "hi": "Hindi",
        "ta": "Tamil",
        "te": "Telugu",
        "kn": "Kannada",
        "ml": "Malayalam",
        "bn": "Bengali",
        "es": "Spanish",
        "ru": "Russian",
        "en": "English",
        "auto": "the detected language",
    }
    target_name = lang_names.get(target_language, target_language)
    source_name = lang_names.get(source_hint, source_hint)

    # Create numbered list of texts to translate
    numbered_texts = "\n".join([f"{i + 1}. {text}" for i, text in enumerate(texts)])

    prompt = f"""Translate the following numbered list of texts from {source_name} to {target_name}.

Context: This is a spiritual/Vedantic teaching by a Hindu monk about Hindu deities, traditions, and sacred places.

RULES:
1. PROPER NOUNS: If a name seems clearly misheard (e.g., "Allama" in a Tamil spiritual context likely means "ella malla"), correct it. Otherwise, transliterate names as-is.
2. REVERENCE: Maintain a respectful, devotional tone. Keep sacred terms (e.g., Bhakti, Dharma, Prasad) in their original form if natural in {target_name}.
3. TTS OPTIMIZED: Use clear punctuation for natural pauses (commas for breaths, periods for full stops). Avoid symbols like *, _, (), or brackets.
4. NATURAL SPEECH: Write for the ear, not the eye. Use conversational {target_name}, not literary or formal style.

Return ONLY a numbered list of translations in the same order.
Format each line as: "number. translation"
No explanations, no notes, no extra text.

Texts to translate:
{numbered_texts}"""

    max_attempts = 1 if is_economy_mode() else 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    top_p=0.8,
                    max_output_tokens=4096,
                ),
            )
            result = response.text.strip()
            if result:
                translations = _parse_batch_response(result, len(texts))
                if translations is not None:
                    return translations
                else:
                    # Count mismatch - trigger fallback to per-segment translation
                    return None
        except Exception as e:
            log("TRANSLATE", f"  Gemini batch attempt {attempt} failed: {e}")
            if _is_quota_exhausted_error(e):
                _mark_quota_exhausted(e)
                raise RuntimeError(f"Gemini batch quota exhausted: {e}")
            time.sleep((1 if is_economy_mode() else 3) * attempt)

    raise RuntimeError(
        f"Gemini batch translation failed after {max_attempts} attempts."
    )


def _translate_segments_per_segment(texts, source_hint, target_language):
    """Fallback: translate texts one by one (original behavior)"""
    log(
        "TRANSLATE",
        f"  Falling back to per-segment translation for {len(texts)} texts...",
    )

    translations = []
    for i, text in enumerate(texts):
        try:
            if target_language == "gu":
                translated = _translate_to_gujarati(text, source_hint)
            else:
                translated = _translate_generic(text, target_language)
        except Exception as e:
            log("TRANSLATE", f"  ERROR on text {i + 1}: {e} — using source text")
            translated = text

        translations.append(translated)

    return translations


def _parse_batch_response(response, expected_count):
    """Parse numbered list response back into individual translations"""
    lines = response.strip().split("\n")
    translations = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Look for "number. translation" format
        if ". " in line:
            parts = line.split(". ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                translations.append(parts[1].strip())
            else:
                # Fallback: take the whole line if format is unexpected
                translations.append(line)
        else:
            translations.append(line)

    # Validate count - if mismatch, return None to trigger fallback
    if len(translations) != expected_count:
        log(
            "TRANSLATE",
            f"  COUNT MISMATCH: expected {expected_count}, got {len(translations)}",
        )
        log(
            "TRANSLATE",
            f"  Gemini may have dropped/merged segments - falling back to per-segment translation",
        )
        return None

    return translations


def _translate_to_gujarati(text, source_hint="auto"):
    # Check cache first
    cached = _get_cached(text, "gu")
    if cached:
        log("TRANSLATE", "[CACHE_HIT] Using cached translation")
        return cached

    if is_economy_mode():
        result = _google_translate_text(
            text, "gu", source_hint=source_hint, use_pivot=True
        )
        _set_cached(text, result or text, "gu")
        return result or text

    result = None
    if _gemini_quota_exhausted:
        _log_skip_once()
    else:
        try:
            result = _gemini_translate(text, source_hint, "gu")
            if (
                result
                and _is_gujarati_script(result)
                and not _has_foreign_script(result)
            ):
                _set_cached(text, result, "gu")
                return result
            log(
                "TRANSLATE",
                "  Gemini output not clean Gujarati — falling back to Google Translate ...",
            )
        except Exception as e:
            if _is_quota_exhausted_error(e):
                _mark_quota_exhausted(e)
            log(
                "TRANSLATE",
                f"  Gemini failed: {e} — falling back to Google Translate ...",
            )

    result = _google_translate_text(
        text, "gu", source_hint=source_hint, use_pivot=False
    )
    if result and _is_gujarati_script(result) and not _has_foreign_script(result):
        _set_cached(text, result, "gu")
        return result

    if source_hint != "en":
        log("TRANSLATE", "  Trying English pivot ...")
        try:
            result2 = _google_translate_text(
                text, "gu", source_hint=source_hint, use_pivot=True
            )
            if (
                result2
                and _is_gujarati_script(result2)
                and not _has_foreign_script(result2)
            ):
                _set_cached(text, result2, "gu")
                return result2
        except Exception as e:
            log("TRANSLATE", f"  Pivot error: {e}")

    log(
        "TRANSLATE",
        "  WARNING: Could not get clean Gujarati — using best available result",
    )
    _set_cached(text, result or text, "gu")
    return result or text


def _translate_to_gujarati_batch(texts, source_hint="auto"):
    """Batch translate multiple texts to Gujarati"""
    if is_economy_mode():
        log(
            "TRANSLATE",
            "  Economy mode: using Google Translate-first routing for batch.",
        )
        return [_translate_to_gujarati(t, source_hint) for t in texts]

    try:
        translations = _gemini_translate_batch(texts, source_hint, "gu")
        if translations is None:
            # Count mismatch - fall back to per-segment translation
            return _translate_segments_per_segment(texts, source_hint, "gu")

        # Validate Gujarati output for each translation
        validated_translations = []
        for translation in translations:
            if (
                translation
                and _is_gujarati_script(translation)
                and not _has_foreign_script(translation)
            ):
                validated_translations.append(translation)
            else:
                validated_translations.append(None)  # Mark for fallback

        # Check if any translations need fallback
        if any(t is None for t in validated_translations):
            log(
                "TRANSLATE",
                "  Some Gemini outputs not clean Gujarati — using fallbacks...",
            )
            # Use individual fallback for problematic translations
            final_translations = []
            for i, (text, validated) in enumerate(zip(texts, validated_translations)):
                if validated is not None:
                    final_translations.append(validated)
                else:
                    # Use individual Google Translate fallback
                    try:
                        from deep_translator import GoogleTranslator

                        if source_hint != "en":
                            english = GoogleTranslator(
                                source="auto", target="en"
                            ).translate(text)
                            result2 = GoogleTranslator(
                                source="en", target="gu"
                            ).translate(english)
                        else:
                            result2 = GoogleTranslator(
                                source="en", target="gu"
                            ).translate(text)
                        final_translations.append(result2)
                    except Exception as e:
                        log("TRANSLATE", f"  Fallback failed for text {i + 1}: {e}")
                        final_translations.append(text)  # Use original as last resort
            return final_translations
        else:
            return translations

    except Exception as e:
        log(
            "TRANSLATE",
            f"  Gemini batch failed: {e} — falling back to per-segment translation",
        )
        return _translate_segments_per_segment(texts, source_hint, "gu")


def _translate_generic(text, target_language):
    # Check cache first
    cached = _get_cached(text, target_language)
    if cached:
        log("TRANSLATE", "[CACHE_HIT] Using cached translation")
        return cached

    if is_economy_mode():
        result = _google_translate_text(
            text, target_language, source_hint="auto", use_pivot=False
        )
        _set_cached(text, result or text, target_language)
        return result or text

    if _gemini_quota_exhausted:
        _log_skip_once()
    else:
        try:
            result = _gemini_translate(text, "auto", target_language)
            _set_cached(text, result, target_language)
            return result
        except Exception as e:
            if _is_quota_exhausted_error(e):
                _mark_quota_exhausted(e)
            log(
                "TRANSLATE",
                f"  Gemini failed for {target_language}: {e} — using Google Translate",
            )
    result = _google_translate_text(
        text, target_language, source_hint="auto", use_pivot=False
    )
    _set_cached(text, result, target_language)
    return result


def _translate_generic_batch(texts, target_language):
    """Batch translate multiple texts to generic language"""
    if is_economy_mode():
        log(
            "TRANSLATE",
            f"  Economy mode: Google Translate-first for target={target_language}.",
        )
        return [_translate_generic(t, target_language) for t in texts]

    try:
        translations = _gemini_translate_batch(texts, "auto", target_language)
        if translations is None:
            # Count mismatch - fall back to per-segment translation
            return _translate_segments_per_segment(texts, "auto", target_language)
        return translations
    except Exception as e:
        log(
            "TRANSLATE",
            f"  Gemini batch failed for {target_language}: {e} — falling back to per-segment translation",
        )
        return _translate_segments_per_segment(texts, "auto", target_language)


def translate_segments(segments, target_language="gu", output_dir="workspace"):
    os.makedirs(output_dir, exist_ok=True)
    _reset_runtime_state()

    source_hint = "auto"
    if segments:
        first_text = segments[0].get("text", "")
        tamil_chars = sum(1 for c in first_text if 0x0B80 <= ord(c) <= 0x0BFF)
        if len(first_text) > 0 and tamil_chars / len(first_text) > 0.10:
            source_hint = "ta"
        else:
            source_hint = "en"

    log("TRANSLATE", f"Source script hint: {source_hint} | Target: {target_language}")
    log("TRANSLATE", f"Batch translating {len(segments)} segments...")

    # Extract all texts for batch translation
    texts = [seg["text"] for seg in segments]

    try:
        # Use batch translation
        if target_language == "gu":
            translations = _translate_to_gujarati_batch(texts, source_hint)
        else:
            translations = _translate_generic_batch(texts, target_language)

        log("TRANSLATE", f"Batch translation completed, processing results...")

    except Exception as e:
        log("TRANSLATE", f"  ERROR: {e} — using source text for all segments")
        translations = texts  # Fallback to original texts

    # Process results and validate
    results = []
    for i, (seg, translated) in enumerate(zip(segments, translations)):
        log("TRANSLATE", f"[{i + 1}/{len(segments)}] {texts[i][:70]}")

        if _has_foreign_script(translated):
            log("TRANSLATE", f"  !! FOREIGN SCRIPT in output — check segment {i + 1}")

        log("TRANSLATE", f"  -> {translated[:70]}")
        log("TRANSLATE", f"     Gujarati script: {_is_gujarati_script(translated)}")
        results.append({**seg, "translated": translated})

    with open(
        os.path.join(output_dir, "translation_log.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if _gemini_quota_exhausted:
        global _last_runtime_meta
        _last_runtime_meta = {
            "used_fallback": True,
            "reason": _gemini_quota_reason or "Gemini quota exhausted",
        }
        log(
            "TRANSLATE",
            "Summary: Gemini quota exhausted in this run; Google Translate fallback was used.",
        )

    # Save translation cache
    _save_cache()

    return results
