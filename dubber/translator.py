import os, json, time
from .utils import log

GUJARATI_RANGE = (0x0A80, 0x0AFF)

NON_GUJARATI_SCRIPTS = [
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0900, 0x097F),  # Devanagari
    (0x0980, 0x09FF),  # Bengali
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
]


def _is_gujarati_script(text):
    if not text: return False
    guj_chars = sum(1 for c in text if GUJARATI_RANGE[0] <= ord(c) <= GUJARATI_RANGE[1])
    return guj_chars / len(text) > 0.25


def _has_foreign_script(text):
    if not text: return False
    for start, end in NON_GUJARATI_SCRIPTS:
        foreign = sum(1 for c in text if start <= ord(c) <= end)
        if foreign / len(text) > 0.10:
            return True
    return False


def _gemini_translate(text, source_hint="auto", target_language="gu"):
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("No Gemini API key found.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    lang_names = {
        "gu": "Gujarati", "hi": "Hindi", "ta": "Tamil",
        "te": "Telugu", "kn": "Kannada", "ml": "Malayalam",
        "en": "English", "auto": "the detected language",
    }
    target_name = lang_names.get(target_language, target_language)

    prompt = f"""Translate the following text to {target_name}.

Context: This is a spiritual/Vedantic teaching by a Hindu monk.
Preserve the teacher's tone and voice.
Use natural spoken {target_name} — not literal word-for-word translation.
Convey the meaning and spiritual register, not just the words.
Return ONLY the translated text. No explanations, no notes.

Text to translate:
{text}"""

    for attempt in range(1, 4):
        try:
            response = model.generate_content(prompt)
            result = response.text.strip()
            if result:
                return result
        except Exception as e:
            log("TRANSLATE", f"  Gemini attempt {attempt} failed: {e}")
            time.sleep(3 * attempt)

    raise RuntimeError("Gemini translation failed after 3 attempts.")


def _translate_to_gujarati(text, source_hint="auto"):
    try:
        result = _gemini_translate(text, source_hint, "gu")
        if result and _is_gujarati_script(result) and not _has_foreign_script(result):
            return result
        log("TRANSLATE", "  Gemini output not clean Gujarati — falling back to Google Translate ...")
    except Exception as e:
        log("TRANSLATE", f"  Gemini failed: {e} — falling back to Google Translate ...")

    from deep_translator import GoogleTranslator

    result = GoogleTranslator(source="auto", target="gu").translate(text)
    if result and _is_gujarati_script(result) and not _has_foreign_script(result):
        return result

    if source_hint != "en":
        log("TRANSLATE", "  Trying English pivot ...")
        try:
            english = GoogleTranslator(source="auto", target="en").translate(text)
            result2 = GoogleTranslator(source="en", target="gu").translate(english)
            if result2 and _is_gujarati_script(result2) and not _has_foreign_script(result2):
                return result2
        except Exception as e:
            log("TRANSLATE", f"  Pivot error: {e}")

    log("TRANSLATE", "  WARNING: Could not get clean Gujarati — using best available result")
    return result or text


def _translate_generic(text, target_language):
    try:
        return _gemini_translate(text, "auto", target_language)
    except Exception as e:
        log("TRANSLATE", f"  Gemini failed for {target_language}: {e} — using Google Translate")
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source="auto", target=target_language).translate(text)


def translate_segments(segments, target_language="gu", output_dir="workspace"):
    os.makedirs(output_dir, exist_ok=True)

    source_hint = "auto"
    if segments:
        first_text = segments[0].get("text", "")
        tamil_chars = sum(1 for c in first_text if 0x0B80 <= ord(c) <= 0x0BFF)
        if len(first_text) > 0 and tamil_chars / len(first_text) > 0.10:
            source_hint = "ta"
        else:
            source_hint = "en"

    log("TRANSLATE", f"Source script hint: {source_hint} | Target: {target_language}")

    results = []
    for i, seg in enumerate(segments):
        src = seg["text"]
        log("TRANSLATE", f"[{i+1}/{len(segments)}] {src[:70]}")
        try:
            if target_language == "gu":
                translated = _translate_to_gujarati(src, source_hint)
            else:
                translated = _translate_generic(src, target_language)
        except Exception as e:
            log("TRANSLATE", f"  ERROR: {e} — using source text")
            translated = src

        if _has_foreign_script(translated):
            log("TRANSLATE", f"  !! FOREIGN SCRIPT in output — check segment {i+1}")

        log("TRANSLATE", f"  -> {translated[:70]}")
        log("TRANSLATE", f"     Gujarati script: {_is_gujarati_script(translated)}")
        results.append({**seg, "translated": translated})

    with open(os.path.join(output_dir, "translation_log.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return results