import argparse
import json
import os
import sys
from typing import Dict, List

import app as app_module
from dubber.caption_generator import generate_all_captions
from dubber.config import load_env_into_process


TARGETS = ["hi", "ta", "bn", "es", "ru"]

SAMPLE_TEXT = {
    "hi": {
        "topic": "जीवित रहते परमशिव रूप में जीना",
        "conflict": "अन्य गुरु बाद की मुक्ति की बात करते हैं, यह शिक्षा अभी जीवन में दिव्यता प्रकट करने की बात करती है।",
        "angle": "जीवित रहते ही परमशिव को प्रकट करो।",
        "line1": "जागरूकता, साहस और भक्ति के साथ जियो।",
        "line2": "जीवित रहते ही परम सत्य को प्रकट करो।",
    },
    "ta": {
        "topic": "உயிரோடு பரமசிவராக வாழுதல்",
        "conflict": "மற்ற ஆசான்கள் பிறகான விடுதலையைப் பேசுகிறார்கள்; இந்த உபதேசம் இப்போதே தெய்வீகத்தை வெளிப்படுத்தச் சொல்கிறது.",
        "angle": "உயிரோடு இருக்கும்போதே பரமசிவத்தை வெளிப்படுத்து.",
        "line1": "விழிப்புணர்வும் துணிவும் பக்தியும் கொண்டு வாழுங்கள்.",
        "line2": "நீங்கள் உயிரோடு இருக்கும்போதே பரம சத்தியத்தை வெளிப்படுத்துங்கள்.",
    },
    "bn": {
        "topic": "জীবিত অবস্থায় পরমশিব হয়ে বাঁচা",
        "conflict": "অন্য গুরু পরে মুক্তির কথা বলেন; এই শিক্ষা এখনই জীবনের মধ্যে ঈশ্বরত্ব প্রকাশ করতে বলে।",
        "angle": "জীবিত অবস্থাতেই পরমশিবকে প্রকাশ করো।",
        "line1": "সচেতনতা, সাহস ও ভক্তি নিয়ে বাঁচো।",
        "line2": "জীবিত থাকতেই সর্বোচ্চ সত্যকে প্রকাশ করো।",
    },
    "es": {
        "topic": "Vivir como Paramashiva mientras estás vivo",
        "conflict": "Otros maestros hablan de la liberación futura; esta enseñanza pide manifestar la divinidad ahora mismo en la vida.",
        "angle": "Manifiesta a Paramashiva mientras aún vives.",
        "line1": "Vive con conciencia, valentía y devoción.",
        "line2": "Manifiesta la verdad suprema mientras estás vivo.",
    },
    "ru": {
        "topic": "Жить как Парамашива уже сейчас",
        "conflict": "Другие учителя говорят о будущем освобождении; это учение призывает проявить божественность прямо сейчас в жизни.",
        "angle": "Проявляй Парамашиву, пока живешь.",
        "line1": "Живи с осознанностью, смелостью и преданностью.",
        "line2": "Проявляй высшую истину, пока ты жив.",
    },
}


def _invert_languages() -> Dict[str, str]:
    return {code: name for name, code in app_module.LANGUAGES.items()}


def _safe_console_text(value: object) -> str:
    text = str(value)
    enc = sys.stdout.encoding or "utf-8"
    return text.encode(enc, errors="replace").decode(enc, errors="replace")


def _sample_vision(language_name: str) -> Dict[str, str]:
    code = app_module.LANGUAGES[language_name]
    sample = SAMPLE_TEXT[code]
    return {
        "main_topic": sample["topic"],
        "core_conflict": sample["conflict"],
        "provocative_angle": sample["angle"],
        "theme": "teaching",
    }


def _sample_segments(code: str) -> List[Dict[str, str]]:
    sample = SAMPLE_TEXT[code]
    return [
        {
            "id": 0,
            "text": sample["line1"],
            "translated": sample["line1"],
        },
        {
            "id": 1,
            "text": sample["line2"],
            "translated": sample["line2"],
        },
    ]


def _check_language(code: str, output_dir: str) -> Dict[str, object]:
    code_to_name = _invert_languages()
    language_name = code_to_name[code]
    default_voice_label = app_module.LANGUAGE_DEFAULT_VOICE.get(language_name, "")
    default_voice_id = app_module.VOICES.get(default_voice_label, "")
    voice_options = [
        label for label in app_module.VOICES.keys() if label.startswith(f"{language_name} -")
    ]

    captions, meta = generate_all_captions(
        _sample_vision(language_name),
        api_key="",
        output_dir=output_dir,
        segments=_sample_segments(code),
        target_language=code,
        return_meta=True,
    )

    youtube_title = captions.get("youtube", {}).get("title", "")
    instagram_caption = captions.get("instagram", {}).get("caption", "")

    checks = {
        "language_present": code in app_module.LANGUAGES.values(),
        "default_voice_label_present": bool(default_voice_label),
        "default_voice_id_present": bool(default_voice_id),
        "voice_options_present": bool(voice_options),
        "captions_have_all_platforms": set(captions.keys()) == set(app_module.PLATFORMS),
        "youtube_title_present": bool(youtube_title.strip()),
        "instagram_caption_present": bool(instagram_caption.strip()),
        "fallback_used": bool(meta.get("used_fallback")),
    }

    ok = all(
        value
        for key, value in checks.items()
        if key != "fallback_used"
    )

    return {
        "ok": ok,
        "language_name": language_name,
        "code": code,
        "default_voice_label": default_voice_label,
        "default_voice_id": default_voice_id,
        "voice_options": voice_options,
        "checks": checks,
        "youtube_title": youtube_title,
        "instagram_caption_preview": instagram_caption[:120],
        "meta": meta,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Quick non-GUI smoke test for multilingual dub language wiring."
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        default=TARGETS,
        help="Target language codes to check. Default: hi ta bn es ru",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join("workspace", "smoke"),
        help="Directory for temporary smoke-test artifacts.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of human summary.",
    )
    args = parser.parse_args()

    load_env_into_process()
    os.environ.pop("MISTRAL_API_KEY", None)
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.makedirs(args.output_dir, exist_ok=True)

    results = []
    for code in args.targets:
        if code not in _invert_languages():
            results.append({
                "ok": False,
                "code": code,
                "error": f"Unsupported target code: {code}",
            })
            continue
        lang_dir = os.path.join(args.output_dir, code)
        os.makedirs(lang_dir, exist_ok=True)
        results.append(_check_language(code, lang_dir))

    overall_ok = all(item.get("ok") for item in results)

    if args.json:
        print(json.dumps({
            "ok": overall_ok,
            "results": results,
        }, ensure_ascii=False, indent=2))
    else:
        print(_safe_console_text("Language Smoke Test"))
        print(_safe_console_text("==================="))
        for item in results:
            status = "PASS" if item.get("ok") else "FAIL"
            code = item.get("code", "?")
            name = item.get("language_name", code)
            print(_safe_console_text(f"{status} {name} ({code})"))
            if item.get("error"):
                print(_safe_console_text(f"  error: {item['error']}"))
                continue
            print(_safe_console_text(f"  default voice: {item['default_voice_label']} -> {item['default_voice_id']}"))
            print(_safe_console_text(f"  voice options: {', '.join(item['voice_options'])}"))
            print(_safe_console_text(f"  youtube title: {item['youtube_title']}"))
            print(_safe_console_text(f"  caption preview: {item['instagram_caption_preview']}"))
            failed_checks = [
                key for key, value in item.get("checks", {}).items()
                if key != "fallback_used" and not value
            ]
            if failed_checks:
                print(_safe_console_text(f"  failed checks: {', '.join(failed_checks)}"))
            print(_safe_console_text(f"  fallback captions used: {item.get('checks', {}).get('fallback_used')}"))

        print(_safe_console_text("==================="))
        print(_safe_console_text(f"OVERALL: {'PASS' if overall_ok else 'FAIL'}"))

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
