import os, shutil, threading, tkinter as tk, concurrent.futures, ctypes
import re
from tkinter import filedialog, ttk, messagebox

import json
import sys

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None
from dubber import (
    transcribe_audio,
    merge_short_segments,
    translate_segments,
    get_translation_runtime_meta,
    generate_tts_audio,
    build_dubbed_video,
    extract_vision,
    generate_all_captions,
    log,
    find_ambiguous_repost_blocks,
    record_ambiguous_publish_results,
)
from dubber.api_validator import validate_all_keys
from dubber.caption_generator import _priority_aware_trim
from dubber.utils import (
    PLATFORMS,
    PLATFORM_LIMITS,
    add_log_subscriber,
    remove_log_subscriber,
    _init_file_logger,
    get_api_call_counts,
    reset_api_call_counts,
    get_log_dir,
)
from dubber.downloader import is_url, download_video
from dubber.bgm_separator import separate_background
from dubber.sdk_publisher import publish_to_platforms_sdk
from dubber.runtime_config import get_pipeline_mode, is_economy_mode, mode_label
from dubber.config import (
    load_env_into_process,
    save_env_updates,
    get_dub_source_lang,
    get_dub_target_lang,
    get_dub_voice,
    get_gemini_api_key,
    get_mistral_api_key,
    get_zernio_api_key,
    get_missing_platform_account_envs,
)
from review_dialog import ReviewDialog

WORKSPACE = "workspace"
OUTPUT_FILE = "output.mp4"

VOICES = {
    "English - Ryan (M)": "en-GB-RyanNeural",
    "English - Sonia (F)": "en-GB-SoniaNeural",
    "Gujarati - Niranjan (M)": "gu-IN-NiranjanNeural",
    "Gujarati - Dhwani (F)": "gu-IN-DhwaniNeural",
    "Hindi - Madhur (M)": "hi-IN-MadhurNeural",
    "Hindi - Swara (F)": "hi-IN-SwaraNeural",
    "Tamil - Valluvar (M)": "ta-IN-ValluvarNeural",
    "Tamil - Pallavi (F)": "ta-IN-PallaviNeural",
    "Telugu - Mohan (M)": "te-IN-MohanNeural",
    "Telugu - Shruti (F)": "te-IN-ShrutiNeural",
    "Kannada - Gagan (M)": "kn-IN-GaganNeural",
    "Kannada - Sapna (F)": "kn-IN-SapnaNeural",
    "Malayalam - Midhun (M)": "ml-IN-MidhunNeural",
    "Malayalam - Sobhana (F)": "ml-IN-SobhanaNeural",
    "Bengali - Pradeep (M)": "bn-BD-PradeepNeural",
    "Bengali - Nabanita (F)": "bn-BD-NabanitaNeural",
    "Spanish (Colombia) - Gonzalo (M)": "es-CO-GonzaloNeural",
    "Russian - Dmitry (M)": "ru-RU-DmitryNeural",
    "Russian - Svetlana (F)": "ru-RU-SvetlanaNeural",
}
LANGUAGES = {
    "English": "en",
    "Hindi": "hi",
    "Gujarati": "gu",
    "Tamil": "ta",
    "Telugu": "te",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Spanish": "es",
    "Russian": "ru",
}
LANGUAGE_DEFAULT_VOICE = {
    "English": "English - Ryan (M)",
    "Gujarati": "Gujarati - Niranjan (M)",
    "Hindi": "Hindi - Madhur (M)",
    "Tamil": "Tamil - Valluvar (M)",
    "Telugu": "Telugu - Mohan (M)",
    "Kannada": "Kannada - Gagan (M)",
    "Malayalam": "Malayalam - Midhun (M)",
    "Bengali": "Bengali - Pradeep (M)",
    "Spanish": "Spanish (Colombia) - Gonzalo (M)",
    "Russian": "Russian - Dmitry (M)",
}

LANGUAGE_CODE_TO_NAME = {code.lower(): name for name, code in LANGUAGES.items()}
VOICE_ID_TO_LABEL = {voice_id: label for label, voice_id in VOICES.items()}

DUB_TOTAL_STAGES = 11


def _stage_text(step, label, total=DUB_TOTAL_STAGES):
    return f"Stage {step}/{total} - {label}"


def _bring_terminal_to_front():
    """Bring the console/terminal window to the foreground (Windows only)."""
    try:
        ctypes.windll.user32.SetForegroundWindow(
            ctypes.windll.kernel32.GetConsoleWindow()
        )
    except Exception:
        pass  # Silently fail if not on Windows or if it doesn't work


def _is_quota_reason(reason):
    s = str(reason or "").lower()
    tokens = (
        "quota",
        "429",
        "resource_exhausted",
        "rate limit",
        "limit: 0",
        "too many requests",
        "exceeded",
        "daily",
    )
    return any(t in s for t in tokens)


def _backup_warning(provider, reason, backup_label):
    if _is_quota_reason(reason):
        return (
            f"⚠️ {provider} quota/rate limit reached. "
            f"Using backup: {backup_label}. Reason: {reason}"
        )
    return f"⚠️ {provider} unavailable. Using backup: {backup_label}. Reason: {reason}"


def _load_env():
    return load_env_into_process()


def _save_env(data):
    save_env_updates(data)


def _resolve_language_name(raw_value, fallback="English"):
    value = str(raw_value or "").strip()
    if not value:
        return fallback
    if value in LANGUAGES:
        return value
    return LANGUAGE_CODE_TO_NAME.get(value.lower(), fallback)


def _resolve_voice_label(raw_value, target_language="English"):
    value = str(raw_value or "").strip()
    if not value:
        return LANGUAGE_DEFAULT_VOICE.get(target_language, list(VOICES.keys())[0])
    if value in VOICES:
        return value
    if value in VOICE_ID_TO_LABEL:
        return VOICE_ID_TO_LABEL[value]
    for label, voice_id in VOICES.items():
        if value.lower() == label.lower() or value.lower() == voice_id.lower():
            return label
    return LANGUAGE_DEFAULT_VOICE.get(target_language, list(VOICES.keys())[0])


def _canonicalize_env_keys(env):
    """Map legacy key names into canonical keys for consistency."""
    updates = {}
    gemini = (
        env.get("GEMINI_API_KEY")
        or env.get("GOOGLE_API_KEY")
        or env.get("GEMINI_VISION_KEY")
        or ""
    ).strip()
    mistral = (
        env.get("MISTRAL_API_KEY") or env.get("OPENROUTER_API_KEY") or ""
    ).strip()
    if gemini and not (env.get("GEMINI_API_KEY") or "").strip():
        updates["GEMINI_API_KEY"] = gemini
    if mistral and not (env.get("MISTRAL_API_KEY") or "").strip():
        updates["MISTRAL_API_KEY"] = mistral
    return updates


def _count_successful_results(results):
    """Count successful platform results, handling error-shaped responses."""
    if not isinstance(results, dict):
        return 0
    if "error" in results and len(results) == 1:
        return 0
    ok = 0
    for v in results.values():
        if isinstance(v, bool):
            ok += 1 if v else 0
            continue
        if not isinstance(v, dict):
            continue
        status = str(v.get("status", "")).lower()
        if status in {
            "ok",
            "published",
            "success",
            "submitted",
            "queued",
            "processing",
            "likely_live",
            "duplicate_live",
        }:
            ok += 1
            continue
        if status in {"error", "failed", "fail"} or "error" in v:
            continue
        # Fallback: some providers may only return IDs for success.
        post_id = (
            v.get("post_id") or v.get("_id") or v.get("id") or v.get("platformPostId")
        )
        if post_id:
            ok += 1
    return ok


def _count_unconfirmed_results(results):
    """Count platform results that are submitted but not confirmed."""
    if not isinstance(results, dict):
        return 0
    unconfirmed = 0
    for v in results.values():
        if not isinstance(v, dict):
            continue
        status = str(v.get("status", "")).lower()
        if status in {"unconfirmed", "submitted_unconfirmed"}:
            unconfirmed += 1
    return unconfirmed


def _count_likely_live_results(results):
    """Count platform results that look like they were already published."""
    if not isinstance(results, dict):
        return 0
    likely_live = 0
    for v in results.values():
        if not isinstance(v, dict):
            continue
        status = str(v.get("status", "")).lower()
        if status in {"likely_live", "duplicate_live"}:
            likely_live += 1
    return likely_live


def _count_skipped_results(results):
    """Count platform results skipped by local preflight rules."""
    if not isinstance(results, dict):
        return 0
    skipped = 0
    for v in results.values():
        if not isinstance(v, dict):
            continue
        status = str(v.get("status", "")).lower()
        if status in {"skipped", "skip"}:
            skipped += 1
    return skipped


def _extract_error_message(results):
    if isinstance(results, dict) and "error" in results:
        return str(results.get("error") or "").strip()
    return ""


def _display_platform_name(platform):
    names = {
        "youtube_hdh_gujarati": "YouTube (HDH Gujarati)",
        "youtube_kailaasa_gujarati": "YouTube (Kailaasa Gujarati)",
    }
    return names.get(str(platform or ""), str(platform or ""))


def _effective_publish_total(selected_platforms, results):
    if not isinstance(results, dict):
        return len(selected_platforms or [])
    resolved = len([key for key in results.keys() if key != "error"])
    return max(len(selected_platforms or []), resolved)


def _expanded_publish_guard_platforms(selected_platforms):
    expanded = []
    for platform in selected_platforms or []:
        if platform == "youtube":
            expanded.extend(["youtube_hdh_gujarati", "youtube_kailaasa_gujarati"])
        else:
            expanded.append(platform)
    return expanded


def _build_flyer_sheet_blurb(flyer_path, workspace_dir=WORKSPACE):
    """Create a short English blurb for sheet column A when publishing images."""
    fallback = os.path.splitext(os.path.basename(flyer_path or "flyer_image"))[0]
    fallback = re.sub(r"[_\-]+", " ", fallback).strip() or "Flyer image"

    text_path = os.path.join(workspace_dir, "flyer_text.txt")
    if not os.path.exists(text_path):
        return fallback

    try:
        with open(text_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return fallback

    ascii_words = re.findall(r"[A-Za-z0-9]+", raw or "")
    if len(ascii_words) < 3:
        return fallback

    # Keep it short and useful in the sheet title column.
    blurb = " ".join(ascii_words[:10]).strip()
    if len(blurb) > 90:
        blurb = blurb[:89].rstrip() + "…"
    return blurb


def _log_api_summary():
    """Log API call summary at end of pipeline."""
    counts = get_api_call_counts()
    log("API_USAGE", f"--- API Call Summary ---")
    log("API_USAGE", f"Gemini API calls: {counts.get('gemini', 0)}")
    log("API_USAGE", f"Mistral API calls: {counts.get('mistral', 0)}")
    log("API_USAGE", f"GLM API calls: {counts.get('glm', 0)}")
    log("API_USAGE", f"Groq API calls: {counts.get('groq', 0)}")
    log("API_USAGE", f"Total API calls: {counts.get('total', 0)}")
    log("API_USAGE", f"------------------------")


def run_dub_pipeline(
    video_input,
    voice,
    model_size,
    src_lang,
    tgt_lang,
    use_bgm,
    bgm_volume,
    gemini_vision_key,
    mistral_key,
    zernio_key,
    selected_platforms,
    publish_now,
    scheduled_for,
    auto_teaser,
    manual_teaser_path,
    image_paths,
    status_cb,
    caption_ready_cb,
    done_cb,
    dub_only=False,
    progress_cb=None,
    output_path=OUTPUT_FILE,
):
    reset_api_call_counts()
    try:
        stage_weights = {
            "download": 0.08,
            "transcribe": 0.22,
            "merge": 0.04,
            "translate": 0.12,
            "tts": 0.12,
            "build_and_vision": 0.24,
            "captions": 0.10,
            "shared_media": 0.08,
        }
        ordered_stages = list(stage_weights.keys())
        cumulative = {}
        total_weight = 0.0
        for stage_name in ordered_stages:
            cumulative[stage_name] = total_weight
            total_weight += stage_weights[stage_name]

        def _emit_stage_progress(stage_name, fraction=1.0):
            if not progress_cb:
                return
            base = cumulative.get(stage_name, 0.0)
            weight = stage_weights.get(stage_name, 0.0)
            pct = round(
                ((base + (weight * max(0.0, min(1.0, fraction)))) / total_weight) * 100
            )
            progress_cb(max(0, min(100, pct)))
            log(
                "PROGRESS",
                f"Progress callback called: {pct}% ({stage_name} {fraction:.2f})",
            )

        shutil.rmtree(WORKSPACE, ignore_errors=True)
        os.makedirs(WORKSPACE, exist_ok=True)

        source_metadata = {}
        if is_url(video_input):
            status_cb("Downloading video ...")
            download_result = download_video(video_input, WORKSPACE)
            if isinstance(download_result, dict):
                video_path = download_result.get("video_path", "")
                source_metadata = download_result.get("source_metadata") or {}
            else:
                video_path = download_result
        else:
            video_path = video_input
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Not found: {video_path}")
        _emit_stage_progress("download", 1.0)

        # PARALLEL GROUP 1: BGM separation + Transcription run simultaneously
        bgm_path = None
        if use_bgm:
            status_cb("Separating background music ...")
        status_cb(_stage_text(1, "Transcribe"))

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            bgm_future = None
            if use_bgm:
                bgm_future = pool.submit(separate_background, video_path, WORKSPACE)
            transcribe_future = pool.submit(
                transcribe_audio, video_path, WORKSPACE, model_size, src_lang
            )

            # Wait for both to finish
            if bgm_future:
                try:
                    bgm_path = bgm_future.result()
                except Exception as e:
                    log("BGM_SEP", f"Parallel BGM failed: {e} — continuing without BGM")
                    bgm_path = None

            segs = transcribe_future.result()

        _emit_stage_progress("transcribe", 1.0)
        status_cb(_stage_text(2, "Merge segments"))
        segs = merge_short_segments(segs)
        _emit_stage_progress("merge", 1.0)
        status_cb(_stage_text(3, "Translate"))
        if is_economy_mode():
            status_cb("ℹ Economy mode: translation uses Google-first routing.")
        else:
            status_cb("ℹ Quality mode: translation uses Gemini-first routing.")
        segs = translate_segments(segs, tgt_lang, WORKSPACE)
        translate_meta = get_translation_runtime_meta()
        if translate_meta.get("used_fallback"):
            status_cb(
                _backup_warning(
                    "Gemini Translate",
                    translate_meta.get("reason", "unknown"),
                    "Google Translate",
                )
            )
        _emit_stage_progress("translate", 1.0)

        # PARALLEL GROUP 2: TTS/Video Build + Vision extraction run simultaneously
        status_cb(_stage_text(4, "Generate TTS"))
        segs = generate_tts_audio(
            segs,
            voice=voice,
            output_dir=WORKSPACE,
        )
        _emit_stage_progress("tts", 1.0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            build_future = pool.submit(
                build_dubbed_video,
                video_path=video_path,
                segments=segs,
                output_path=output_path,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                output_dir=WORKSPACE,
            )
            vision_future = pool.submit(
                extract_vision, segs, gemini_vision_key, WORKSPACE, True, tgt_lang
            )

            build_future.result()  # wait for video build
            vision, vision_meta = vision_future.result()

        _emit_stage_progress("build_and_vision", 1.0)
        if vision_meta.get("used_fallback"):
            status_cb(
                _backup_warning(
                    "Gemini Vision",
                    vision_meta.get("reason", "unknown"),
                    "rule-based intelligence",
                )
            )

        if dub_only:
            status_cb(f"Dub-only mode complete. Output: {output_path}")
            _log_api_summary()
            _emit_stage_progress("shared_media", 1.0)
            done_cb(success=True, msg="Dubbing complete.", pub_results={})
            return

        status_cb(_stage_text(7, "Generate captions"))
        captions, caption_meta = generate_all_captions(
            vision,
            mistral_key,
            WORKSPACE,
            segments=segs,
            target_language=tgt_lang,
            return_meta=True,
            selected_platforms=selected_platforms,
            source_metadata=source_metadata,
        )
        _emit_stage_progress("captions", 1.0)
        if caption_meta.get("used_fallback"):
            status_cb(
                _backup_warning(
                    "Mistral Caption API",
                    caption_meta.get("reason", "unknown"),
                    "template captions",
                )
            )

        if auto_teaser or manual_teaser_path:
            log(
                "PIPELINE",
                "Teaser clip generation is disabled in the standard publish flow. "
                "Using the shared dubbed video for every platform.",
            )
        status_cb(_stage_text(8, "Use shared dubbed video"))
        _emit_stage_progress("shared_media", 1.0)

        status_cb(_stage_text(9, "Review captions"))
        _log_api_summary()
        caption_ready_cb(
            captions=captions,
            video_path=output_path,
            zernio_key=zernio_key,
            selected_platforms=selected_platforms,
            publish_now=publish_now,
            scheduled_for=scheduled_for,
            image_paths=image_paths,
            done_cb=done_cb,
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        done_cb(success=False, msg=str(e), pub_results={})


def run_publish_only(
    image_paths,
    teaser_path,
    topic_hint,
    gemini_vision_key,
    mistral_key,
    zernio_key,
    selected_platforms,
    publish_now,
    scheduled_for,
    status_cb,
    caption_ready_cb,
    done_cb,
):
    try:
        os.makedirs(WORKSPACE, exist_ok=True)

        if mistral_key and topic_hint.strip():
            status_cb("Generating captions from topic hint ...")
            vision = {
                "main_topic": topic_hint.strip(),
                "core_conflict": topic_hint.strip(),
                "provocative_angle": topic_hint.strip(),
                "festival": "None",
                "location": "None",
                "date": "None",
                "theme": "teaching",
            }
            captions, caption_meta = generate_all_captions(
                vision,
                mistral_key,
                WORKSPACE,
                return_meta=True,
                selected_platforms=selected_platforms,
            )
            if caption_meta.get("used_fallback"):
                status_cb(
                    _backup_warning(
                        "Mistral Caption API",
                        caption_meta.get("reason", "unknown"),
                        "template captions",
                    )
                )
        else:
            status_cb("Opening caption review for manual entry ...")
            captions = {p: {"caption": ""} for p in selected_platforms}
            for p in selected_platforms:
                if p == "youtube":
                    captions[p]["title"] = ""

        status_cb("Waiting for caption review ...")
        primary_image = image_paths[0] if image_paths else ""
        caption_ready_cb(
            captions=captions,
            teaser_path=teaser_path,
            video_path="",
            main_image_path=primary_image,
            zernio_key=zernio_key,
            selected_platforms=selected_platforms,
            publish_now=publish_now,
            scheduled_for=scheduled_for,
            image_paths=image_paths,
            done_cb=done_cb,
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        done_cb(success=False, msg=str(e), pub_results={})


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Dubber v1.26")
        self.geometry("700x720")
        self.minsize(620, 620)
        self.resizable(True, True)

        log_dir = get_log_dir()
        log_file = _init_file_logger()
        log("APP", f"Logging to: {log_file}")
        log("APP", f"Log directory: {log_dir}")

        self._env = _load_env()
        canonical_updates = _canonicalize_env_keys(self._env)
        if canonical_updates:
            _save_env(canonical_updates)
            self._env.update(canonical_updates)
        self._image_paths = []
        self._header_photo = None
        self._publish_state_lock = threading.Lock()
        self._dub_publish_active = False
        self._flyer_publish_active = False
        self._init_theme()
        self._build_ui()

    def _build_mode_selector(self, parent, row, title, hint):
        pad = {"padx": 12, "pady": 4}
        tk.Label(parent, text=title, font=("Segoe UI Semibold", 10)).grid(
            row=row, column=0, sticky="w", **pad
        )
        wrap = tk.Frame(parent, bg=self._colors["panel"])
        wrap.grid(row=row, column=1, columnspan=2, sticky="w", **pad)
        tk.Radiobutton(
            wrap,
            text="Economy",
            variable=self.pipeline_mode_var,
            value="economy",
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 12))
        tk.Radiobutton(
            wrap,
            text="Quality",
            variable=self.pipeline_mode_var,
            value="quality",
            font=("Segoe UI", 9),
        ).pack(side="left")
        tk.Label(
            parent,
            text=hint,
            fg=self._colors["muted"],
            font=("Segoe UI", 8),
        ).grid(row=row + 1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))
        return row + 2

    def _init_theme(self):
        self._colors = {
            "bg": "#F9F5EF",  # Sandstone BG
            "panel": "#F4EFE6",  # Surface
            "input": "#EDE6D8",  # Surface 2
            "muted": "#6B5740",  # Warm Muted
            "text": "#1E1209",  # Deep Ink
            "border": "#D5C8B0",  # Stone Border
            "primary": "#7B1F1F",  # Kaavi
            "primary_dark": "#5A1515",  # Kaavi Dark
            "accent": "#C8860A",  # Sacred Gold
            "accent_bright": "#E8A020",  # Gold Bright
            "success": "#2C5F2E",  # Dharma Green
            "danger": "#E8700A",  # Saffron
        }
        self.configure(bg=self._colors["bg"])

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Modern.TNotebook", background=self._colors["bg"], borderwidth=0
        )
        style.configure(
            "Modern.TNotebook.Tab",
            padding=(18, 8),
            font=("Segoe UI", 10, "bold"),
            background=self._colors["primary_dark"],
            foreground="white",
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Modern.TNotebook.Tab",
            background=[
                ("selected", self._colors["primary"]),
                ("active", self._colors["primary_dark"]),
                ("!selected", self._colors["primary_dark"]),
            ],
            foreground=[
                ("selected", "white"),
                ("active", "white"),
                ("!selected", "white"),
            ],
            bordercolor=[
                ("selected", self._colors["primary"]),
                ("active", self._colors["primary_dark"]),
                ("!selected", self._colors["primary_dark"]),
            ],
            lightcolor=[
                ("selected", self._colors["primary"]),
                ("active", self._colors["primary_dark"]),
                ("!selected", self._colors["primary_dark"]),
            ],
            darkcolor=[
                ("selected", self._colors["primary"]),
                ("active", self._colors["primary_dark"]),
                ("!selected", self._colors["primary_dark"]),
            ],
            expand=[
                ("selected", [1, 1, 1, 0]),
                ("active", [1, 1, 1, 0]),
                ("!selected", [1, 1, 1, 0]),
            ],
        )
    def _style_text_area(self, widget):
        widget.configure(
            bg=self._colors["input"],
            fg=self._colors["text"],
            insertbackground=self._colors["text"],
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=self._colors["border"],
            highlightcolor=self._colors["accent_bright"],
            padx=8,
            pady=8,
            wrap="word",
        )

    def _create_scrollable_tab(self, tab_frame):
        """Create a vertically scrollable area inside a notebook tab."""
        tab_frame.grid_rowconfigure(0, weight=1)
        tab_frame.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(
            tab_frame,
            bg=self._colors["panel"],
            highlightthickness=0,
            bd=0,
        )
        v_scroll = ttk.Scrollbar(tab_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")

        body = tk.Frame(canvas, bg=self._colors["panel"])
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)

        def _on_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")

        def _bind_mousewheel(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_mousewheel(_event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        body.bind("<Enter>", _bind_mousewheel)
        body.bind("<Leave>", _unbind_mousewheel)

        return body

    def _set_panel_bg(self, parent):
        for child in parent.winfo_children():
            if isinstance(child, tk.Frame):
                child.configure(bg=self._colors["panel"])
                self._set_panel_bg(child)
            elif isinstance(child, tk.Label):
                child.configure(bg=self._colors["panel"], fg=self._colors["text"])
            elif isinstance(child, (tk.Checkbutton, tk.Radiobutton)):
                child.configure(
                    bg=self._colors["panel"],
                    fg=self._colors["text"],
                    activebackground=self._colors["panel"],
                    activeforeground=self._colors["text"],
                    selectcolor=self._colors["input"],
                )

    def _bind_button_states(self, button, normal, hover=None, pressed=None, fg="white"):
        """Apply consistent hover/pressed states for tk.Button widgets."""
        hover = hover or normal
        pressed = pressed or hover
        button.configure(
            bg=normal,
            fg=fg,
            activebackground=pressed,
            activeforeground=fg,
        )

        def _on_enter(_event):
            if str(button.cget("state")) == "disabled":
                return
            button.configure(bg=hover)

        def _on_leave(_event):
            if str(button.cget("state")) == "disabled":
                return
            button.configure(bg=normal)

        def _on_press(_event):
            if str(button.cget("state")) == "disabled":
                return
            button.configure(bg=pressed)

        def _on_release(_event):
            if str(button.cget("state")) == "disabled":
                return
            inside = (
                button.winfo_containing(
                    button.winfo_pointerx(), button.winfo_pointery()
                )
                == button
            )
            button.configure(bg=hover if inside else normal)

        button.bind("<Enter>", _on_enter)
        button.bind("<Leave>", _on_leave)
        button.bind("<ButtonPress-1>", _on_press)
        button.bind("<ButtonRelease-1>", _on_release)

    def _set_flyer_publish_ready(self, ready, reason=""):
        """Enable Publish Content only after successful flyer processing."""
        self._flyer_publish_ready = bool(ready)
        if hasattr(self, "publish_flyer_btn"):
            if ready:
                self.publish_flyer_btn.config(
                    state="normal",
                    bg=self._colors["success"],
                    disabledforeground="#f3f4f6",
                )
            else:
                self.publish_flyer_btn.config(
                    state="disabled", bg="#9ca3af", disabledforeground="#f3f4f6"
                )
        if reason and hasattr(self, "status_var"):
            self.status_var.set(reason)

    def _fit_caption_for_platform(self, platform, caption):
        """Trim caption to platform character limits when needed."""
        limit = PLATFORM_LIMITS.get(platform)
        if limit is None:
            return self._normalize_caption_text(caption), False, None
        text = self._normalize_caption_text(caption)
        if len(text) <= limit:
            return text, False, limit
        trimmed = _priority_aware_trim(text, limit, platform)
        return trimmed, True, limit

    def _normalize_caption_text(self, caption):
        """Remove stray quote artifacts and keep hashtags on a new line."""
        text = str(caption or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        text = re.sub(r'^[\s"“”\'‘’`]+', "", text)
        text = re.sub(r'[\s"“”\'‘’`]+$', "", text)
        if "#" in text:
            i = text.find("#")
            if i > 0:
                head = text[:i].rstrip()
                tags = text[i:].lstrip()
                if head and not head.endswith("\n"):
                    text = f"{head}\n\n{tags}"
                elif head:
                    text = f"{head}\n{tags}"
                else:
                    text = tags
        return re.sub(r"\n{3,}", "\n\n", text)

    def _translate_title_to_english(self, text):
        """Best-effort Gujarati->English translation for sheet title formatting."""
        if not text:
            return ""
        try:
            from deep_translator import GoogleTranslator

            translated = GoogleTranslator(source="auto", target="en").translate(text)
            return (translated or "").strip()
        except Exception:
            return ""

    def _get_media_duration_text(self, media_path):
        """Return HH:MM:SS or MM:SS for sheet logging."""
        if not media_path or not os.path.exists(media_path):
            return ""
        try:
            from dubber.video_builder import _ffprobe_duration

            total_seconds = int(round(float(_ffprobe_duration(media_path))))
            hours, rem = divmod(total_seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            if hours:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return f"{minutes:02d}:{seconds:02d}"
        except Exception:
            return ""

    def _build_video_sheet_title(self, approved_captions, video_path):
        """Return `Target-language Title (English Title)` with caption fallback."""
        fallback = os.path.splitext(os.path.basename(video_path))[0]
        gujarati_title = ""

        if isinstance(approved_captions, dict):
            youtube = approved_captions.get("youtube", {})
            if isinstance(youtube, dict):
                gujarati_title = (youtube.get("title") or "").strip()

            if not gujarati_title:
                for platform in (
                    "instagram",
                    "facebook",
                    "threads",
                    "twitter",
                    "tiktok",
                    "bluesky",
                ):
                    pdata = approved_captions.get(platform, {})
                    caption = ""
                    if isinstance(pdata, dict):
                        caption = (pdata.get("caption") or "").strip()
                    elif isinstance(pdata, str):
                        caption = pdata.strip()
                    if caption:
                        first_line = caption.splitlines()[0].strip()
                        main_part = first_line.split("#")[0].strip()
                        sentence_parts = [
                            part.strip()
                            for part in re.split(r"[.!?\n]+", main_part)
                            if part.strip()
                        ]
                        gujarati_title = (
                            sentence_parts[0] if sentence_parts else main_part
                        )
                        if gujarati_title:
                            break

        if not gujarati_title:
            return fallback
        english_title = self._translate_title_to_english(gujarati_title)
        if english_title:
            return f"{gujarati_title} ({english_title})"
        return gujarati_title

    def _queue_ui(self, fn):
        """Queue a callback on Tk UI thread; return False if UI loop is unavailable."""
        try:
            self.after(0, fn)
            return True
        except RuntimeError:
            return False

    def _start_activity_mirror(self, kind):
        """Reflect long-running flyer activity in the status bar without relying on Tk internals."""
        if kind != "flyer":
            return
        self._flyer_status_before_activity = self.status_var.get()
        self.status_var.set("Processing flyer...")
        for widget_name in ("process_flyer_btn", "publish_flyer_btn"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                try:
                    widget.config(state="disabled")
                except Exception:
                    pass
        try:
            self.configure(cursor="watch")
            self.update_idletasks()
        except Exception:
            pass

    def _stop_activity_mirror(self, kind):
        """Restore flyer UI state after processing or publishing completes."""
        if kind != "flyer":
            return
        widget = getattr(self, "process_flyer_btn", None)
        if widget is not None:
            try:
                widget.config(state="normal")
            except Exception:
                pass
        if getattr(self, "_flyer_publish_ready", False):
            self._set_flyer_publish_ready(True)
        else:
            self._set_flyer_publish_ready(False)
        try:
            self.configure(cursor="")
            self.update_idletasks()
        except Exception:
            pass

    def _try_begin_publish(self, kind):
        """Return True only for the first active publish of a given kind."""
        with self._publish_state_lock:
            if kind == "dub":
                if self._dub_publish_active:
                    return False
                self._dub_publish_active = True
                return True
            if kind == "flyer":
                if self._flyer_publish_active:
                    return False
                self._flyer_publish_active = True
                return True
            return False

    def _end_publish(self, kind):
        with self._publish_state_lock:
            if kind == "dub":
                self._dub_publish_active = False
            elif kind == "flyer":
                self._flyer_publish_active = False

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}
        self.status_var = tk.StringVar(value=f"Ready. {mode_label()}.")

        header = tk.Frame(self, bg=self._colors["panel"], relief="solid", bd=1)
        header.pack(fill="x", padx=16, pady=(14, 8))
        header_left = tk.Frame(header, bg=self._colors["panel"])
        header_left.pack(side="left", fill="both", expand=True, padx=14, pady=10)
        tk.Label(
            header_left,
            text="AutoDub Studio",
            bg=self._colors["panel"],
            fg=self._colors["text"],
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")
        tk.Label(
            header_left,
            text="Dub videos and publish multilingual content with a guided review flow.",
            bg=self._colors["panel"],
            fg=self._colors["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(2, 0))

        header_right = tk.Frame(header, bg=self._colors["panel"])
        header_right.pack(side="right", padx=12, pady=8)
        img_path = r"C:\Users\Sri Paramashivatma\Pictures\swamijiprofile_picture-bg removed.png"
        if Image is not None and ImageTk is not None and os.path.exists(img_path):
            try:
                img = Image.open(img_path).convert("RGBA")
                img.thumbnail((88, 88), Image.Resampling.LANCZOS)
                self._header_photo = ImageTk.PhotoImage(img)
                tk.Label(
                    header_right,
                    image=self._header_photo,
                    bg=self._colors["panel"],
                    bd=0,
                    highlightthickness=0,
                ).pack()
            except Exception:
                pass

        self.nb = ttk.Notebook(self, style="Modern.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=16, pady=6)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.t_dub_tab = tk.Frame(self.nb, bg=self._colors["panel"], padx=0, pady=0)
        self.nb.add(self.t_dub_tab, text="  Dub Video  ")
        self.t_dub = self._create_scrollable_tab(self.t_dub_tab)
        self.t_dub.configure(padx=16, pady=12)
        self.t_dub.grid_columnconfigure(1, weight=1)
        self.pipeline_mode_var = tk.StringVar(value=get_pipeline_mode())
        default_src_lang = _resolve_language_name(get_dub_source_lang(), "English")
        default_tgt_lang = _resolve_language_name(get_dub_target_lang(), "English")
        default_voice_label = _resolve_voice_label(
            get_dub_voice(), target_language=default_tgt_lang
        )

        tk.Label(
            self.t_dub, text="1) Source Input", font=("Segoe UI Semibold", 11)
        ).grid(row=0, column=0, sticky="w", **pad)
        tk.Label(self.t_dub, text="Video / URL:", font=("Segoe UI", 10)).grid(
            row=1, column=0, sticky="w", **pad
        )
        self.video_var = tk.StringVar()
        tk.Entry(
            self.t_dub, textvariable=self.video_var, width=44, relief="solid", bd=1
        ).grid(row=1, column=1, **pad)
        tk.Button(
            self.t_dub,
            text="Browse",
            command=self._browse_video,
            width=10,
            bg=self._colors["input"],
            fg=self._colors["text"],
            relief="solid",
            bd=1,
        ).grid(row=1, column=2, **pad)
        next_row = self._build_mode_selector(
            self.t_dub,
            row=2,
            title="Pipeline mode:",
            hint="Economy saves API cost and skips heavier retries. Quality spends more calls for better recovery.",
        )

        tk.Label(
            self.t_dub, text="2) Language & Voice", font=("Segoe UI Semibold", 11)
        ).grid(row=next_row, column=0, sticky="w", **pad)
        tk.Label(self.t_dub, text="Voice:", font=("Segoe UI", 10)).grid(
            row=next_row + 1, column=0, sticky="w", **pad
        )
        self.voice_var = tk.StringVar(value=default_voice_label)
        self.voice_combo = ttk.Combobox(
            self.t_dub,
            textvariable=self.voice_var,
            values=list(VOICES.keys()),
            width=30,
            state="readonly",
        )
        self.voice_combo.grid(row=next_row + 1, column=1, sticky="w", **pad)

        tk.Label(self.t_dub, text="Source lang:", font=("Segoe UI", 10)).grid(
            row=next_row + 2, column=0, sticky="w", **pad
        )
        self.src_lang_var = tk.StringVar(value=default_src_lang)
        ttk.Combobox(
            self.t_dub,
            textvariable=self.src_lang_var,
            values=list(LANGUAGES.keys()),
            width=16,
            state="readonly",
        ).grid(row=next_row + 2, column=1, sticky="w", **pad)

        tk.Label(self.t_dub, text="Target lang:", font=("Segoe UI", 10)).grid(
            row=next_row + 3, column=0, sticky="w", **pad
        )
        self.tgt_lang_var = tk.StringVar(value=default_tgt_lang)
        self.tgt_lang_combo = ttk.Combobox(
            self.t_dub,
            textvariable=self.tgt_lang_var,
            values=list(LANGUAGES.keys()),
            width=16,
            state="readonly",
        )
        self.tgt_lang_combo.grid(row=next_row + 3, column=1, sticky="w", **pad)
        self.tgt_lang_combo.bind(
            "<<ComboboxSelected>>", self._on_target_language_changed
        )
        self._sync_voice_options()

        tk.Label(
            self.t_dub,
            font=("Segoe UI", 8),
        ).grid(
            row=next_row + 5, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6)
        )

        ttk.Separator(self.t_dub, orient="horizontal").grid(
            row=next_row + 6, column=0, columnspan=3, sticky="ew", pady=8
        )
        self.dub_only_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self.t_dub,
            text="Dub only — skip platform captions and publishing",
            variable=self.dub_only_var,
            font=("Segoe UI", 9),
        ).grid(row=next_row + 7, column=0, columnspan=3, sticky="w", **pad)

        ttk.Separator(self.t_dub, orient="horizontal").grid(
            row=next_row + 8, column=0, columnspan=3, sticky="ew", pady=8
        )
        tk.Label(
            self.t_dub,
            text="3) Audio Blend & Platforms",
            font=("Segoe UI Semibold", 11),
        ).grid(row=next_row + 9, column=0, sticky="w", **pad)
        self.bgm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.t_dub,
            text="Preserve background music (Demucs)",
            variable=self.bgm_var,
            command=self._toggle_bgm,
        ).grid(row=next_row + 9, column=0, columnspan=2, sticky="w", **pad)
        tk.Label(self.t_dub, text="Music volume:", font=("Segoe UI", 10)).grid(
            row=next_row + 10, column=0, sticky="w", **pad
        )
        self.bgm_vol_var = tk.DoubleVar(value=0.35)
        self.bgm_scale = tk.Scale(
            self.t_dub,
            variable=self.bgm_vol_var,
            from_=0.0,
            to=1.0,
            resolution=0.05,
            orient="horizontal",
            length=220,
            bg=self._colors["panel"],
            fg=self._colors["text"],
            highlightthickness=0,
        )
        self.bgm_scale.grid(row=next_row + 10, column=1, sticky="w", **pad)

        tk.Label(self.t_dub, text="Platforms to publish:", font=("Segoe UI", 10)).grid(
            row=next_row + 11, column=0, sticky="w", **pad
        )
        self._plat_vars = {}
        pf = tk.Frame(self.t_dub, bg=self._colors["panel"])
        pf.grid(row=next_row + 11, column=1, columnspan=2, sticky="w")
        for i, p in enumerate(PLATFORMS):
            v = tk.BooleanVar(value=True)
            self._plat_vars[p] = v
            tk.Checkbutton(
                pf, text=p.capitalize(), variable=v, font=("Segoe UI", 9)
            ).grid(row=i // 4, column=i % 4, sticky="w", padx=6)

        ttk.Separator(self.t_dub, orient="horizontal").grid(
            row=next_row + 14, column=0, columnspan=3, sticky="ew", pady=8
        )
        self.t_media_tab = tk.Frame(self.nb, bg=self._colors["panel"], padx=0, pady=0)
        self.nb.add(self.t_media_tab, text="  Flyer / Image  ")
        self.t_media = self._create_scrollable_tab(self.t_media_tab)
        self.t_media.configure(padx=16, pady=12)
        self.t_media.grid_columnconfigure(1, weight=1)

        tk.Label(
            self.t_media, text="Flyer/Image Processing", font=("Segoe UI Semibold", 12)
        ).grid(row=0, column=0, columnspan=3, sticky="w", **pad)
        tk.Label(
            self.t_media,
            text="Upload flyers/posters to extract text and generate Gujarati content",
            fg=self._colors["muted"],
            font=("Segoe UI", 9),
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))
        media_row = self._build_mode_selector(
            self.t_media,
            row=2,
            title="Pipeline mode:",
            hint="This also affects flyer OCR and caption-generation fallbacks.",
        )

        ttk.Separator(self.t_media, orient="horizontal").grid(
            row=media_row, column=0, columnspan=3, sticky="ew", pady=8
        )

        tk.Label(
            self.t_media, text="Select Flyer/Images:", font=("Segoe UI Semibold", 10)
        ).grid(row=media_row + 1, column=0, sticky="w", **pad)
        self.flyer_var = tk.StringVar()
        tk.Entry(
            self.t_media, textvariable=self.flyer_var, width=54, relief="solid", bd=1
        ).grid(row=media_row + 1, column=1, **pad)
        tk.Button(
            self.t_media,
            text="Browse",
            command=self._browse_flyer,
            width=10,
            bg=self._colors["input"],
            fg=self._colors["text"],
            relief="solid",
            bd=1,
        ).grid(row=media_row + 1, column=2, **pad)

        self.flyer_paths = []
        self.flyer_count_label = tk.Label(
            self.t_media, text="", fg=self._colors["muted"], font=("Segoe UI", 8)
        )
        self.flyer_count_label.grid(
            row=media_row + 2, column=0, columnspan=3, sticky="w", padx=12
        )

        ttk.Separator(self.t_media, orient="horizontal").grid(
            row=media_row + 3, column=0, columnspan=3, sticky="ew", pady=8
        )
        tk.Label(
            self.t_media, text="Processing Options:", font=("Segoe UI Semibold", 10)
        ).grid(row=media_row + 4, column=0, sticky="w", **pad)

        self.extract_text_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.t_media,
            text="Extract text from flyer/image",
            variable=self.extract_text_var,
            font=("Segoe UI", 9),
        ).grid(row=media_row + 5, column=0, columnspan=3, sticky="w", padx=12)

        self.generate_captions_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.t_media,
            text="Generate platform captions",
            variable=self.generate_captions_var,
            font=("Segoe UI", 9),
        ).grid(row=media_row + 6, column=0, columnspan=3, sticky="w", padx=12)

        self.generate_teaser_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.t_media,
            text="Create teaser content",
            variable=self.generate_teaser_var,
            font=("Segoe UI", 9),
        ).grid(row=media_row + 7, column=0, columnspan=3, sticky="w", padx=12)

        ttk.Separator(self.t_media, orient="horizontal").grid(
            row=media_row + 8, column=0, columnspan=3, sticky="ew", pady=8
        )
        bf = tk.Frame(self.t_media, bg=self._colors["panel"])
        bf.grid(row=media_row + 9, column=0, columnspan=3, sticky="w", padx=12)
        tk.Button(
            bf,
            text="Clear Selection",
            command=self._clear_flyer,
            bg=self._colors["input"],
            fg=self._colors["text"],
            relief="solid",
            bd=1,
        ).pack(side="left", padx=4)

        tk.Label(
            self.t_media, text="Processing activity", font=("Segoe UI Semibold", 10)
        ).grid(row=media_row + 10, column=0, sticky="w", **pad)
        self.flyer_results = tk.Text(
            self.t_media, width=84, height=8, font=("Consolas", 9)
        )
        self.flyer_results.grid(
            row=media_row + 11,
            column=0,
            columnspan=3,
            padx=12,
            pady=(0, 8),
            sticky="nsew",
        )
        self.t_media.grid_rowconfigure(media_row + 11, weight=1)
        self._style_text_area(self.flyer_results)

        ttk.Separator(self.t_media, orient="horizontal").grid(
            row=media_row + 12, column=0, columnspan=3, sticky="ew", pady=8
        )
        tk.Label(
            self.t_media, text="Platforms to Publish:", font=("Segoe UI Semibold", 10)
        ).grid(row=media_row + 13, column=0, sticky="w", **pad)
        self._flyer_plat_vars = {}
        pf = tk.Frame(self.t_media, bg=self._colors["panel"])
        pf.grid(row=media_row + 13, column=1, columnspan=2, sticky="w")
        for i, p in enumerate(PLATFORMS):
            if p not in ["youtube", "tiktok"]:
                v = tk.BooleanVar(value=True)
                self._flyer_plat_vars[p] = v
                tk.Checkbutton(
                    pf, text=p.capitalize(), variable=v, font=("Segoe UI", 9)
                ).grid(row=i // 4, column=i % 4, sticky="w", padx=6)

        ttk.Separator(self.t_media, orient="horizontal").grid(
            row=media_row + 14, column=0, columnspan=3, sticky="ew", pady=8
        )
        self._flyer_publish_ready = False

        # Bottom action bar
        bot = tk.Frame(
            self, bg=self._colors["panel"], relief="solid", bd=1, padx=10, pady=8
        )
        bot.pack(side="bottom", fill="x", padx=16, pady=(6, 10))

        self.cleanup_btn = tk.Button(
            bot,
            text="Clean Workspace",
            width=14,
            bg=self._colors["danger"],
            fg="white",
            font=("Segoe UI Semibold", 9),
            command=self._manual_cleanup,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
        )
        self.cleanup_btn.pack(side="left", padx=6)

        self.review_fixes_btn = tk.Button(
            bot,
            text="Review Fixes",
            width=12,
            bg=self._colors["accent"],
            fg="white",
            font=("Segoe UI Semibold", 9),
            command=self._review_transcription_fixes,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
        )
        self.review_fixes_btn.pack(side="left", padx=6)

        center_frame = tk.Frame(bot, bg=self._colors["panel"])
        center_frame.pack(side="left", expand=True, fill="x", padx=12)

        self.process_flyer_btn = tk.Button(
            center_frame,
            text="Process Flyer",
            command=self._process_flyer,
            bg=self._colors["accent"],
            fg="white",
            width=14,
            font=("Segoe UI Semibold", 9),
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
        )
        self.process_flyer_btn.pack(side="left", padx=4)

        self.publish_flyer_btn = tk.Button(
            center_frame,
            text="Publish Content",
            command=self._publish_flyer_content,
            bg=self._colors["success"],
            fg="white",
            width=14,
            font=("Segoe UI Semibold", 9),
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
        )
        self.publish_flyer_btn.pack(side="left", padx=4)

        self.run_btn = tk.Button(
            bot,
            text="Run Dub Pipeline",
            width=16,
            bg=self._colors["primary"],
            fg="white",
            font=("Segoe UI Semibold", 9),
            command=self._run,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
        )
        self.run_btn.pack(side="right", padx=6)
        self._bind_button_states(
            self.run_btn,
            normal=self._colors["primary"],
            hover=self._colors["primary_dark"],
            pressed=self._colors["primary_dark"],
            fg="white",
        )
        self._bind_button_states(
            self.process_flyer_btn,
            normal=self._colors["accent"],
            hover=self._colors["accent_bright"],
            pressed=self._colors["accent_bright"],
            fg="white",
        )
        self._bind_button_states(
            self.publish_flyer_btn,
            normal=self._colors["success"],
            hover=self._colors["primary_dark"],
            pressed=self._colors["primary_dark"],
            fg="white",
        )
        self._bind_button_states(
            self.cleanup_btn,
            normal=self._colors["danger"],
            hover=self._colors["primary_dark"],
            pressed=self._colors["primary_dark"],
            fg="white",
        )

        self.process_flyer_btn.pack_forget()
        self.publish_flyer_btn.pack_forget()
        self._set_flyer_publish_ready(False)

        status_frame = tk.Frame(self, bg=self._colors["panel"], relief="solid", bd=1)
        status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            fg=self._colors["text"],
            bg=self._colors["panel"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        status_label.pack(side="left", padx=8, pady=5, fill="x", expand=True)
        status_frame.pack(side="bottom", fill="x", padx=16, pady=(0, 12))

        # Store flyer path
        self.flyer_path = ""
        self._dub_log_listener = None
        self._flyer_log_listener = None

        # Initialize API key variables (hidden from GUI)
        self.gemini_vision_key_var = tk.StringVar(value=get_gemini_api_key())
        self.mistral_key_var = tk.StringVar(value=get_mistral_api_key())
        self.zernio_key_var = tk.StringVar(value=get_zernio_api_key())

        # Initialize missing variables from Publish Only tab
        self.topic_var = tk.StringVar()
        self.pub_teaser_var = tk.StringVar()
        self._image_paths = []
        self.pipeline_mode_var.trace_add("write", self._on_pipeline_mode_changed)
        self._set_panel_bg(self.t_dub)
        self._set_panel_bg(self.t_media)

    def _on_tab_changed(self, event):
        """Handle tab changes - hide/show buttons based on selected tab"""
        # Skip if this is the initial load (no event object)
        if event is None:
            return

        selected_tab = self.nb.index(self.nb.select())
        if selected_tab == 1:  # Flyer/Image tab
            # Show Process Flyer and Publish Generated buttons
            self.process_flyer_btn.pack(side="left", padx=4)
            self.publish_flyer_btn.pack(side="left", padx=4)
            # Hide Run Pipeline button
            self.run_btn.pack_forget()
        else:  # Dub tab
            # Hide Process Flyer and Publish Generated buttons
            self.process_flyer_btn.pack_forget()
            self.publish_flyer_btn.pack_forget()
            # Show Run Pipeline button
            self.run_btn.pack(side="right", padx=6)

    def _voice_options_for_language(self, language_name):
        prefix = f"{language_name} -"
        prefix2 = f"{language_name} ("
        matches = [
            label
            for label in VOICES.keys()
            if label.startswith(prefix) or label.startswith(prefix2)
        ]
        return matches or list(VOICES.keys())

    def _sync_voice_options(self):
        target_language = self.tgt_lang_var.get() or "English"
        options = self._voice_options_for_language(target_language)
        if hasattr(self, "voice_combo"):
            self.voice_combo["values"] = options
        current = self.voice_var.get().strip()
        if current not in options:
            self.voice_var.set(LANGUAGE_DEFAULT_VOICE.get(target_language, options[0]))

    def _on_target_language_changed(self, event=None):
        self._sync_voice_options()

    def _on_pipeline_mode_changed(self, *_args):
        mode = (self.pipeline_mode_var.get() or "economy").strip().lower()
        if mode not in {"economy", "quality"}:
            mode = "economy"
            self.pipeline_mode_var.set(mode)
            return
        _save_env({"PIPELINE_MODE": mode})
        self._env["PIPELINE_MODE"] = mode
        if hasattr(self, "status_var"):
            self.status_var.set(f"Pipeline mode set to {mode.capitalize()}.")

    def _toggle_bgm(self):
        self.bgm_scale.config(state="normal" if self.bgm_var.get() else "disabled")

    def _clear_flyer(self):
        """Clear flyer selection and results"""
        self.flyer_var.set("")
        self.flyer_path = ""
        self.flyer_paths = []  # Clear multiple images
        self.flyer_count_label.config(text="")
        self.flyer_results.delete(1.0, tk.END)
        self._set_flyer_publish_ready(
            False, "Flyer cleared. Process flyer to enable publishing."
        )

    def _update_flyer_results(self, message):
        """Update flyer results with new message"""
        self.flyer_results.insert(tk.END, f"{message}\n")
        self.flyer_results.see(tk.END)

    def _browse_video(self):
        """Browse for video file"""
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("All files", "*.*"),
            ],
        )
        if file_path:
            self.video_var.set(file_path)

    def _browse_flyer(self):
        """Browse for flyer/image files (multiple selection)"""
        file_paths = filedialog.askopenfilenames(
            title="Select Flyer/Images (Ctrl+Click for multiple)",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ],
        )
        if file_paths:
            self.flyer_paths = list(file_paths)
            if len(file_paths) == 1:
                self.flyer_var.set(file_paths[0])
                self.flyer_count_label.config(text="")
            else:
                self.flyer_var.set(f"{len(file_paths)} images selected")
                # Show first few filenames
                preview = ", ".join([os.path.basename(p) for p in file_paths[:3]])
                if len(file_paths) > 3:
                    preview += f" +{len(file_paths) - 3} more"
                self.flyer_count_label.config(text=preview)

            # Store single path for compatibility
            self.flyer_path = file_paths[0]
            self._set_flyer_publish_ready(
                False, "Flyer selected. Process flyer to enable publishing."
            )

    def _process_flyer(self):
        """Process flyer to extract text and generate content"""
        if not self.flyer_path:
            messagebox.showerror("Error", "Please select a flyer/image file first")
            return

        if not os.path.exists(self.flyer_path):
            messagebox.showerror("Error", "File not found")
            return

        try:
            self._set_flyer_publish_ready(False, "Processing flyer...")
            self.flyer_results.delete(1.0, tk.END)
            self.flyer_results.insert(tk.END, "🔄 Processing flyer...\n\n")
            self._start_activity_mirror("flyer")
            _save_env(
                {
                    "PIPELINE_MODE": self.pipeline_mode_var.get().strip().lower()
                    or "economy"
                }
            )

            # Get API keys
            gemini_key = self.gemini_vision_key_var.get().strip()

            extracted_text = ""
            captions = {}
            teaser = {}

            # Extract text from image
            if self.extract_text_var.get():
                self.flyer_results.insert(tk.END, "📝 Extracting text from image...\n")
                try:
                    from dubber.image_processor import extract_text_from_image

                    extracted_text = extract_text_from_image(
                        self.flyer_path, gemini_key
                    )
                    self.flyer_results.insert(
                        tk.END, f"✅ Extracted {len(extracted_text)} characters\n"
                    )
                    self.flyer_results.insert(
                        tk.END,
                        f"Text: {extracted_text[:200]}{'...' if len(extracted_text) > 200 else ''}\n\n",
                    )
                except Exception as e:
                    self.flyer_results.insert(
                        tk.END, f"❌ Text extraction failed: {str(e)}\n\n"
                    )

            # Generate platform captions
            if self.generate_captions_var.get() and extracted_text:
                try:
                    from dubber.image_processor import generate_platform_captions

                    target_name = self.tgt_lang_var.get().strip() or "English"
                    target_language = LANGUAGES.get(target_name, "en")
                    self.flyer_results.insert(
                        tk.END, f"🎨 Generating {target_name} captions...\n"
                    )
                    captions = generate_platform_captions(
                        extracted_text,
                        target_language=target_language,
                        api_key=gemini_key,
                    )
                    if isinstance(captions, dict) and "error" not in captions:
                        self.flyer_results.insert(
                            tk.END, "✅ Generated captions for all platforms\n"
                        )
                        for platform, caption in captions.items():
                            self.flyer_results.insert(
                                tk.END,
                                f"  {platform.title()}: {caption[:100]}{'...' if len(caption) > 100 else ''}\n",
                            )
                    else:
                        self.flyer_results.insert(
                            tk.END, f"❌ Caption generation failed: {captions}\n"
                        )
                    self.flyer_results.insert(tk.END, "\n")
                except Exception as e:
                    self.flyer_results.insert(
                        tk.END, f"❌ Caption generation failed: {str(e)}\n\n"
                    )

            # Generate teaser content
            if self.generate_teaser_var.get() and extracted_text:
                self.flyer_results.insert(tk.END, "🎬 Creating teaser content...\n")
                try:
                    from dubber.image_processor import generate_teaser_content

                    teaser = generate_teaser_content(
                        extracted_text,
                        captions,
                        api_key=gemini_key,
                        target_language=LANGUAGES.get(
                            self.tgt_lang_var.get().strip() or "English", "en"
                        ),
                    )
                    if isinstance(teaser, dict) and "error" not in teaser:
                        self.flyer_results.insert(
                            tk.END, "✅ Generated teaser content\n"
                        )
                        for key, value in teaser.items():
                            self.flyer_results.insert(
                                tk.END, f"  {key.replace('_', ' ').title()}: {value}\n"
                            )
                    else:
                        self.flyer_results.insert(
                            tk.END, f"❌ Teaser generation failed: {teaser}\n"
                        )
                    self.flyer_results.insert(tk.END, "\n")
                except Exception as e:
                    self.flyer_results.insert(
                        tk.END, f"❌ Teaser generation failed: {str(e)}\n\n"
                    )

            self.flyer_results.insert(tk.END, "🎉 Processing complete!\n")

            # Save results to workspace
            if extracted_text or captions or teaser:
                workspace_dir = "workspace"
                os.makedirs(workspace_dir, exist_ok=True)

                # Save extracted text
                if extracted_text:
                    with open(
                        os.path.join(workspace_dir, "flyer_text.txt"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(extracted_text)

                # Save captions
                if captions and isinstance(captions, dict):
                    with open(
                        os.path.join(workspace_dir, "flyer_captions.json"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        json.dump(captions, f, ensure_ascii=False, indent=2)

                # Save teaser
                if teaser and isinstance(teaser, dict):
                    with open(
                        os.path.join(workspace_dir, "flyer_teaser.json"),
                        "w",
                        encoding="utf-8",
                    ) as f:
                        json.dump(teaser, f, ensure_ascii=False, indent=2)

                self.flyer_results.insert(
                    tk.END, f"💾 Results saved to {workspace_dir}/ folder\n"
                )

                # Auto-cleanup after 30 seconds if enabled
                if hasattr(self, "auto_cleanup_var") and self.auto_cleanup_var.get():
                    self.flyer_results.insert(
                        tk.END, f"⏰ Auto-cleanup in 30 seconds...\n"
                    )
                    self.after(30000, lambda: self._delayed_cleanup(workspace_dir))
                else:
                    self.flyer_results.insert(
                        tk.END,
                        f"💡 Files will remain - use '🧹 Clean' button when ready\n",
                    )

            captions_ok = (
                isinstance(captions, dict)
                and bool(captions)
                and "error" not in captions
            )
            if captions_ok:
                self._set_flyer_publish_ready(True, "Flyer ready. You can publish now.")
            else:
                self._set_flyer_publish_ready(
                    False,
                    "Captions not ready. Fix processing issues before publishing.",
                )

        except Exception as e:
            messagebox.showerror("Error", f"Failed to process flyer: {str(e)}")
            self.flyer_results.insert(tk.END, f"❌ Error: {str(e)}\n")
            self._set_flyer_publish_ready(
                False, "Processing failed. Publish remains disabled."
            )
        finally:
            self._stop_activity_mirror("flyer")

    def _publish_flyer_content(self):
        """Publish the generated flyer content"""
        try:
            if not getattr(self, "_flyer_publish_ready", False):
                messagebox.showwarning(
                    "Not Ready",
                    "Process flyer first. Publish is enabled only after successful processing.",
                )
                return
            if not self._try_begin_publish("flyer"):
                messagebox.showwarning(
                    "Already Publishing",
                    "A flyer publish is already in progress. Please wait.",
                )
                return
            # Check if captions exist
            captions_file = os.path.join("workspace", "flyer_captions.json")
            if not os.path.exists(captions_file):
                self._end_publish("flyer")
                messagebox.showerror(
                    "No Content", "Please process the flyer first to generate captions!"
                )
                return

            # Load captions
            with open(captions_file, "r", encoding="utf-8") as f:
                captions = json.load(f)

            # Check if flyer image exists
            if not self.flyer_path or not os.path.exists(self.flyer_path):
                self._end_publish("flyer")
                messagebox.showerror("No Image", "Please select a flyer image first!")
                return

            # Get selected platforms from flyer tab (already excludes video-only platforms)
            selected = [p for p, v in self._flyer_plat_vars.items() if v.get()]
            print(f"DEBUG: Selected flyer platforms: {selected}")

            if not selected:
                self._end_publish("flyer")
                messagebox.showwarning(
                    "No Platforms",
                    "Please select at least one image-compatible platform (Instagram, Facebook, X, Threads, Bluesky)!\n\nNote: YouTube and TikTok don't support image publishing.",
                )
                return

            # Get API keys
            zernio_key = self.zernio_key_var.get().strip()
            if not zernio_key:
                self._end_publish("flyer")
                messagebox.showerror(
                    "No API Key", "Please enter Zernio API key in AI & Publish tab!"
                )
                return

            # Prepare captions for publishing (needed for both live and test mode)
            publish_captions = {}
            adjusted_platforms = []
            for platform in selected:
                raw_caption = captions.get(platform)
                if isinstance(raw_caption, dict):
                    raw_caption = raw_caption.get("caption", "")
                if raw_caption is None:
                    raw_caption = (
                        f"Check out this content from KAILASA! #KAILASA #Nithyananda"
                    )
                fitted_caption, adjusted, limit = self._fit_caption_for_platform(
                    platform, raw_caption
                )
                if adjusted:
                    adjusted_platforms.append((platform, len(str(raw_caption)), limit))
                if platform in captions:
                    publish_captions[platform] = {"caption": fitted_caption}
                else:
                    publish_captions[platform] = {"caption": fitted_caption}

            if adjusted_platforms:
                self.flyer_results.insert(
                    tk.END, "✂️ Caption length adjusted for platform limits:\n"
                )
                for platform, original_len, limit in adjusted_platforms:
                    self.flyer_results.insert(
                        tk.END,
                        f"  - {platform.title()}: {original_len} → {limit} chars\n",
                    )
                self.flyer_results.insert(tk.END, "\n")
                self.flyer_results.see(tk.END)

            self.status_var.set("Review flyer captions — edit if needed, then approve.")
            flyer_dialog_captions = {
                platform: publish_captions.get(platform, {"caption": ""})
                for platform in selected
            }
            dlg = ReviewDialog(
                self, flyer_dialog_captions, upload_manager=None, platforms=selected
            )
            if dlg.result is None:
                self._end_publish("flyer")
                self.status_var.set("Flyer publishing cancelled.")
                return
            publish_captions = dlg.result

            # Start publishing
            self.status_var.set("Publishing flyer...")
            self._start_activity_mirror("flyer")
            _save_env(
                {
                    "PIPELINE_MODE": self.pipeline_mode_var.get().strip().lower()
                    or "economy"
                }
            )
            publish_now_flag = True
            flyer_paths = list(self.flyer_paths)
            primary_flyer = flyer_paths[0] if flyer_paths else self.flyer_path
            additional_flyers = flyer_paths[1:] if len(flyer_paths) > 1 else []

            def _publish_thread():
                try:
                    # Publish to platforms using NEW SDK publisher
                    results = publish_to_platforms_sdk(
                        api_key=zernio_key,
                        video_path=None,  # No video for flyers
                        captions=publish_captions,
                        platforms=selected,
                        publish_now=publish_now_flag,
                        image_paths=flyer_paths,  # Pass all selected images
                        output_dir="workspace",
                        progress_cb=lambda done, total, platform, status: (
                            self._queue_ui(
                                lambda: self._update_progress(
                                    done, total, platform, status
                                )
                            )
                        ),
                        fallback_files={
                            "main_image": primary_flyer,
                            "additional_images": additional_flyers,
                        },  # Pass all images for upload
                    )

                    # Count successful publishes correctly (ignore top-level {"error": "..."} payloads)
                    successful = _count_successful_results(results)

                    self._queue_ui(
                        lambda: self._flyer_publish_done(
                            successful, len(selected), results
                        )
                    )

                except Exception as e:
                    self._queue_ui(
                        lambda: self._flyer_publish_done(0, 1, {"error": str(e)})
                    )
                finally:
                    self._end_publish("flyer")

            threading.Thread(target=_publish_thread, daemon=True).start()

        except Exception as e:
            self._end_publish("flyer")
            self._stop_activity_mirror("flyer")
            messagebox.showerror("Error", f"Failed to publish: {str(e)}")

    def _test_flyer_publish(self, platforms, captions):
        """Test mode - show what would be published without actually posting"""
        test_info = "🧪 TEST MODE - No actual publishing\n\n"
        test_info += f"Platforms: {', '.join(platforms)}\n"
        test_info += f"Image: {os.path.basename(self.flyer_path)}\n\n"

        test_info += "Captions that would be posted:\n"
        test_info += "=" * 50 + "\n"

        for platform in platforms:
            caption = captions.get(platform, {}).get("caption", "No caption found")
            # Show full caption without truncation for test mode
            test_info += f"\n📱 {platform.upper()}:\n{caption}\n"

        # Show debug info about media
        test_info += "\n" + "=" * 50 + "\n"
        test_info += "DEBUG: Media analysis\n"
        test_info += f"Primary media: {self.flyer_path}\n"
        test_info += f"Media type: image\n"
        test_info += f"Extra images: 0 (empty array)\n"
        test_info += f"Total media items that would be sent: 1\n"

        # Display in results text area
        self.flyer_results.delete(1.0, tk.END)
        self.flyer_results.insert(tk.END, test_info)

        messagebox.showinfo(
            "Test Mode Complete",
            "Test mode complete - no actual posts were made.\nCheck the Results section for details.",
        )
        self.status_var.set("Test mode completed")

    def _flyer_publish_done(self, successful, total, results):
        """Handle flyer publishing completion"""
        self._stop_activity_mirror("flyer")
        self.flyer_results.insert(tk.END, "\n📊 Publish Results:\n")
        self.flyer_results.insert(tk.END, "=" * 40 + "\n")
        failure_lines = []
        success_lines = []
        unconfirmed_lines = []
        unconfirmed = _count_unconfirmed_results(results)
        for platform, result in results.items():
            if isinstance(result, dict):
                status = str(result.get("status", "")).lower()
                post_id = result.get("post_id") or result.get("_id") or "n/a"
                if status in {"unconfirmed", "submitted_unconfirmed"}:
                    err_msg = (
                        result.get("error")
                        or result.get("error_message")
                        or "Publish status unconfirmed"
                    )
                    unconfirmed_lines.append(f"⚠️ {platform}: {err_msg}")
                    continue
                if status in {
                    "ok",
                    "published",
                    "success",
                    "submitted",
                    "queued",
                    "processing",
                }:
                    success_lines.append(f"✅ {platform}: {post_id}")
                else:
                    err_msg = (
                        result.get("error")
                        or result.get("error_message")
                        or "Unknown error"
                    )
                    failure_lines.append(f"❌ {platform}: {err_msg}")
            elif isinstance(result, bool):
                if result:
                    success_lines.append(f"✅ {platform}: success")
                else:
                    failure_lines.append(f"❌ {platform}: skipped")
            else:
                failure_lines.append(f"❌ {platform}: unexpected result format")

        for line in success_lines + unconfirmed_lines + failure_lines:
            self.flyer_results.insert(tk.END, line + "\n")
        self.flyer_results.see(tk.END)

        if successful > 0:
            self.status_var.set(f"Published to {successful}/{total} platforms!")
            if failure_lines:
                msg = (
                    f"Published to {successful}/{total} platform(s).\n\n"
                    f"Failures:\n" + "\n".join(failure_lines[:5])
                )
                messagebox.showinfo("Partial Success", msg)
            else:
                messagebox.showinfo(
                    "Success", f"Successfully published to {successful} platform(s)!"
                )

            # Log to Google Sheet after successful flyer publish
            try:
                from dubber.sheet_logger import quick_update_from_publish_result

                formatted_title = _build_flyer_sheet_blurb(self.flyer_path, WORKSPACE)

                # Call sheet logger for image publishing
                sheet_success, sheet_msg = quick_update_from_publish_result(
                    video_title=formatted_title,
                    publish_results=results,
                    duration="N/A",  # N/A for images
                    source_lang="English",  # Flyers are treated as English source content
                    target_lang="Gujarati",  # Flyers are always Gujarati output
                    content_format="Image",  # Images publishing
                )
                print(f"[SHEET] Flyer publish: {sheet_msg}")

            except Exception as e:
                print(f"[SHEET] Flyer sheet update failed: {e}")

        elif unconfirmed > 0:
            self.status_var.set("Publish submitted but unconfirmed")
            warn_msg = (
                f"Publish request was sent, but confirmation is unverified for {unconfirmed}/{total} platform(s).\n\n"
                "Zernio returned an empty/invalid response. Please check platform dashboards before retrying to avoid duplicates."
            )
            messagebox.showwarning("Unconfirmed Publish", warn_msg)
            # Still update Google Sheet to track this attempt and mark unconfirmed status.
            try:
                from dubber.sheet_logger import quick_update_from_publish_result

                formatted_title = _build_flyer_sheet_blurb(self.flyer_path, WORKSPACE)

                sheet_success, sheet_msg = quick_update_from_publish_result(
                    video_title=formatted_title,
                    publish_results=results,
                    duration="N/A",
                    source_lang="English",
                    target_lang="Gujarati",
                    content_format="Image",
                )
                print(f"[SHEET] Flyer publish (unconfirmed): {sheet_msg}")
            except Exception as e:
                print(f"[SHEET] Flyer sheet update failed (unconfirmed): {e}")
        else:
            self.status_var.set("Publishing failed")
            error_msg = (
                "\n".join(failure_lines[:6])
                if failure_lines
                else "Publishing failed. Check API keys and try again."
            )
            messagebox.showerror("Failed", error_msg)

        # Log results
        for platform, result in results.items():
            if isinstance(result, dict) and "error" in result:
                print(f"FAIL {platform}: {result['error']}")
            elif isinstance(result, bool):
                # Handle case where result is a boolean (from skip logic)
                status = "skipped" if not result else "success"
                print(f"OK   {platform}: {status}")
            else:
                # Normal case - result is a dict with post info
                post_id = (
                    result.get("_id", "success")
                    if isinstance(result, dict)
                    else "success"
                )
                print(f"OK   {platform}: {post_id}")

    def _delayed_cleanup(self, workspace_dir):
        """Delayed cleanup after timer expires"""
        try:
            from dubber.workspace_cleaner import cleanup_flyer_files

            cleanup_flyer_files(workspace_dir)
            self.flyer_results.insert(tk.END, f"🧹 Auto-cleanup completed\n")
        except Exception as e:
            self.flyer_results.insert(tk.END, f"⚠️ Auto-cleanup failed: {str(e)}\n")

    def _manual_cleanup(self):
        """Manual workspace cleanup"""
        try:
            from dubber.workspace_cleaner import full_cleanup

            self.status_var.set("Cleaning workspace...")
            full_cleanup("workspace")
            self.status_var.set("Workspace cleaned successfully!")
            messagebox.showinfo("Cleanup", "Workspace has been cleaned up!")
        except Exception as e:
            self.status_var.set(f"Cleanup failed: {str(e)}")
            messagebox.showerror(
                "Cleanup Failed", f"Failed to clean workspace: {str(e)}"
            )

    def _review_transcription_fixes(self):
        """Show minimal dialog to review and approve pending transcription fixes."""
        try:
            from dubber.transcriber import get_pending_fixes, approve_fixes

            pending = get_pending_fixes()
            if not pending:
                messagebox.showinfo(
                    "No Fixes", "No pending transcription fixes to review."
                )
                return

            # Create simple dialog
            dialog = tk.Toplevel(self)
            dialog.title("Review Transcription Fixes")
            dialog.geometry("400x300")
            dialog.transient(self)
            dialog.grab_set()

            tk.Label(
                dialog,
                text=f"Pending fixes ({len(pending)}):",
                font=("Segoe UI", 10, "bold"),
            ).pack(pady=(10, 5))

            # Listbox with fixes
            listbox = tk.Listbox(dialog, width=50, height=10)
            listbox.pack(padx=10, pady=5, fill="both", expand=True)

            for word, correction in pending.items():
                listbox.insert(tk.END, f"'{word}' → '{correction}'")

            # Button frame
            btn_frame = tk.Frame(dialog)
            btn_frame.pack(pady=10)

            def approve_selected():
                selected = listbox.curselection()
                if not selected:
                    messagebox.showwarning(
                        "No Selection", "Please select fixes to approve."
                    )
                    return

                words_to_approve = {}
                for idx in selected:
                    item = listbox.get(idx)
                    if "→" in item:
                        parts = item.split("→")
                        if len(parts) == 2:
                            word = parts[0].strip().strip("'")
                            correction = parts[1].strip().strip("'")
                            words_to_approve[word] = correction

                if words_to_approve:
                    count = approve_fixes(words_to_approve)
                    messagebox.showinfo("Success", f"Approved {count} fix(es).")
                    dialog.destroy()

            def approve_all():
                count = approve_fixes(pending)
                messagebox.showinfo("Success", f"Approved all {count} fix(es).")
                dialog.destroy()

            tk.Button(
                btn_frame,
                text="Approve Selected",
                command=approve_selected,
                bg=self._colors["success"],
                fg="white",
            ).pack(side="left", padx=5)

            tk.Button(
                btn_frame,
                text="Approve All",
                command=approve_all,
                bg=self._colors["accent"],
                fg="white",
            ).pack(side="left", padx=5)

            tk.Button(
                btn_frame,
                text="Close",
                command=dialog.destroy,
            ).pack(side="left", padx=5)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to review fixes: {str(e)}")

    def _save_keys(self):
        to_save = {}
        if self.gemini_vision_key_var.get().strip():
            to_save["GEMINI_API_KEY"] = self.gemini_vision_key_var.get().strip()
        if self.mistral_key_var.get().strip():
            to_save["MISTRAL_API_KEY"] = self.mistral_key_var.get().strip()
        if self.zernio_key_var.get().strip():
            to_save["ZERNIO_API_KEY"] = self.zernio_key_var.get().strip()
        to_save["PIPELINE_MODE"] = (
            self.pipeline_mode_var.get().strip().lower() or "economy"
        )
        if to_save:
            _save_env(to_save)
        self.status_var.set("Keys saved.")

    def _run(self):
        # Bring terminal to front so user can see logs
        _bring_terminal_to_front()

        # Always run dub pipeline since mode selection is removed
        video = self.video_var.get().strip()
        if not video:
            messagebox.showwarning("No input", "Paste a URL or browse for a video.")
            return
        self.run_btn.config(state="disabled")
        self.status_var.set("Validating API connections ...")

        selected = [p for p, v in self._plat_vars.items() if v.get()]
        # No scheduling implemented yet - always publish immediately
        sched = None
        gemini_vision = self.gemini_vision_key_var.get().strip()
        mistral = self.mistral_key_var.get().strip()
        zernio = self.zernio_key_var.get().strip()

        # Pre-flight API validation (Groq is optional — local Whisper is default)
        validation = validate_all_keys(
            gemini_key=gemini_vision,
            mistral_key=mistral,
            zernio_key=zernio,
            groq_key=None,
            need_captions=not self.dub_only_var.get(),
            need_publish=not self.dub_only_var.get(),
        )

        # Check for hard failures (only required APIs)
        errors = {k: v for k, v in validation.items() if v["status"] == "error"}
        if errors:
            error_lines = []
            for svc, info in validation.items():
                icon = {"ok": "✅", "error": "❌", "missing": "⏭️"}.get(
                    info["status"], "❓"
                )
                label = {
                    "groq": "Groq",
                    "gemini": "Gemini",
                    "mistral": "Mistral",
                    "zernio": "Zernio",
                }.get(svc, svc)
                error_lines.append(f"{icon} {label}: {info['message']}")

            msg = "\n".join(error_lines)
            proceed = messagebox.askokcancel(
                "API Connection Issues",
                f"⚠️ Some API checks failed:\n\n{msg}\n\nContinue anyway?",
            )
            if not proceed:
                self.status_var.set("Aborted — API validation failed")
                self.run_btn.config(state="normal")
                return
        to_save = {}
        if gemini_vision:
            to_save["GEMINI_API_KEY"] = gemini_vision
        if mistral:
            to_save["MISTRAL_API_KEY"] = mistral
        if zernio:
            to_save["ZERNIO_API_KEY"] = zernio
        to_save["PIPELINE_MODE"] = (
            self.pipeline_mode_var.get().strip().lower() or "economy"
        )
        if to_save:
            _save_env(to_save)

        # Teaser clips are disabled for the shared-video publish flow.
        manual_teaser = ""

        # Create custom status callback for dub results
        def dub_status_callback(message, progress_pct=None):
            def _apply():
                # Keep status bar aligned with pipeline activity stages/warnings.
                if str(message).startswith("Stage ") or str(message).startswith("⚠"):
                    self.status_var.set(message)

            self.after(0, _apply)

        def progress_callback(pct):
            return None

        # Test callback immediately
        dub_status_callback("🔄 Initializing dub pipeline...")

        def safe_done_callback(success, msg, pub_results=None):
            self.after(0, lambda: self._done_cb(success, msg, pub_results))

        threading.Thread(
            target=run_dub_pipeline,
            args=(
                video,
                VOICES[self.voice_var.get()],
                "large",  # Always use whisper-large-v3 for best quality
                LANGUAGES[self.src_lang_var.get()],
                LANGUAGES[self.tgt_lang_var.get()],
                self.bgm_var.get(),
                self.bgm_vol_var.get(),
                gemini_vision,
                mistral,
                zernio,
                selected,
                True,
                sched,
                False,
                manual_teaser,
                list(self._image_paths),
                dub_status_callback,
                self._caption_ready_cb,
                safe_done_callback,
                self.dub_only_var.get(),
                progress_callback,  # progress_cb — separate function for percentage updates
            ),
            daemon=True,
        ).start()

    def _caption_ready_cb(self, **kwargs):
        self.after(0, lambda: self._show_review(**kwargs))

    def _show_review(
        self,
        captions,
        teaser_path=None,
        video_path="",
        main_image_path=None,
        zernio_key="",
        selected_platforms=None,
        publish_now=True,
        scheduled_for=None,
        image_paths=None,
        done_cb=None,
        teaser_paths=None,
    ):
        self.status_var.set("Review platform-specific captions, then approve.")

        # Show review dialog (simplified without parallel uploads for now)
        dlg = ReviewDialog(
            self, captions, upload_manager=None, platforms=selected_platforms
        )
        if dlg.result is None:
            self.run_btn.config(state="normal")
            self.status_var.set("Publishing cancelled.")
            return
        approved = dlg.result
        if not self._try_begin_publish("dub"):
            self.status_var.set("A publish is already in progress. Please wait.")
            return

        missing_account_envs = get_missing_platform_account_envs(selected_platforms)
        missing_account_envs.pop("bluesky", None)
        missing_account_envs.pop("youtube", None)
        if missing_account_envs:
            self._end_publish("dub")
            missing_lines = "\n".join(
                f"- {platform}: {env_name}"
                for platform, env_name in missing_account_envs.items()
            )
            msg = (
                "Publishing is blocked because Zernio platform account IDs are not configured.\n\n"
                "Add these keys to your .env:\n"
                f"{missing_lines}"
            )
            self.status_var.set("Publishing blocked: missing Zernio account IDs.")
            self.run_btn.config(state="normal")
            messagebox.showerror("Missing Zernio Account IDs", msg)
            return

        media_guard_path = (
            video_path
            or main_image_path
            or ((image_paths or [None])[0] if image_paths else None)
        )
        repost_blocks = find_ambiguous_repost_blocks(
            media_guard_path,
            approved,
            _expanded_publish_guard_platforms(selected_platforms),
        )
        if repost_blocks:
            self._end_publish("dub")
            lines = "\n".join(
                f"- {_display_platform_name(item['platform'])}: previous {item['status']} at {item['timestamp']}"
                for item in repost_blocks
            )
            msg = (
                "Publishing is blocked because this exact content was already submitted on these platforms.\n\n"
                "Please verify the live profiles/dashboards before reposting:\n"
                f"{lines}"
            )
            self.status_var.set("Duplicate-protection blocked repost.")
            self.run_btn.config(state="normal")
            messagebox.showwarning("Duplicate Protection", msg)
            return

        def _safe_done(success, msg, pub_results=None):
            if done_cb:
                if not self._queue_ui(
                    lambda: done_cb(success=success, msg=msg, pub_results=pub_results)
                ):
                    try:
                        done_cb(success=success, msg=msg, pub_results=pub_results)
                    except Exception:
                        pass

        self.status_var.set(_stage_text(10, "Publish"))

        # Thread-safe progress callback for status bar updates
        def _thread_safe_progress(done, total, platform, status):
            """Thread-safe progress update for status bar"""
            self._queue_ui(lambda: self._update_progress(done, total, platform, status))

        def _publish():
            try:
                if video_path:
                    fallback_files = {"main_video": video_path}
                else:
                    all_images = list(image_paths or [])
                    primary_image = main_image_path or (all_images[0] if all_images else None)
                    additional_images = list(all_images)
                    if (
                        primary_image
                        and additional_images
                        and additional_images[0] == primary_image
                    ):
                        additional_images = additional_images[1:]
                if not video_path:
                    fallback_files = {
                        "main_image": primary_image,
                        "additional_images": additional_images,
                    }
                results = publish_to_platforms_sdk(
                    api_key=zernio_key,
                    video_path=video_path,
                    captions=approved,
                    platforms=selected_platforms,
                    scheduled_for=scheduled_for if not publish_now else None,
                    publish_now=publish_now,
                    image_paths=image_paths,
                    output_dir=WORKSPACE,
                    progress_cb=_thread_safe_progress,
                    fallback_files=fallback_files,
                )

                error_msg = _extract_error_message(results)
                ok = _count_successful_results(results)
                unconfirmed = _count_unconfirmed_results(results)
                likely_live = _count_likely_live_results(results)
                skipped = _count_skipped_results(results)
                total = _effective_publish_total(selected_platforms, results)
                if error_msg:
                    msg = f"Publishing blocked: {error_msg}"
                elif skipped > 0 and likely_live > 0 and unconfirmed > 0:
                    msg = (
                        f"Published {ok}/{total} platform(s); {likely_live} likely already live, "
                        f"{unconfirmed} unconfirmed, {skipped} skipped by platform limits."
                    )
                elif skipped > 0 and likely_live > 0:
                    msg = (
                        f"Published {ok}/{total} platform(s); {likely_live} likely already live and "
                        f"{skipped} skipped by platform limits."
                    )
                elif skipped > 0 and unconfirmed > 0:
                    msg = (
                        f"Published {ok}/{total} platform(s); {unconfirmed} unconfirmed and "
                        f"{skipped} skipped by platform limits."
                    )
                elif skipped > 0:
                    msg = f"Published {ok}/{total} platform(s); {skipped} skipped by platform limits."
                elif likely_live > 0 and unconfirmed > 0:
                    msg = (
                        f"Published {ok}/{total} platform(s); {likely_live} likely already live and "
                        f"{unconfirmed} still unconfirmed. Check dashboard before retrying."
                    )
                elif likely_live > 0:
                    msg = (
                        f"Published {ok}/{total} platform(s); {likely_live} likely already live "
                        "from a duplicate Bluesky response."
                    )
                elif ok > 0 and unconfirmed > 0:
                    msg = (
                        f"Published {ok}/{total} platform(s); {unconfirmed} unconfirmed. "
                        "Check dashboard before retrying."
                    )
                elif ok > 0:
                    msg = f"Published {ok}/{total} platform(s)."
                elif unconfirmed > 0:
                    msg = (
                        f"Publish submitted but unconfirmed for {unconfirmed}/{total} platform(s). "
                        "Check dashboard before retrying."
                    )
                else:
                    msg = f"Published 0/{total} platform(s)."

                # Log to Google Sheet after successful or unconfirmed publish
                if not error_msg and (ok > 0 or unconfirmed > 0):
                    try:
                        self._queue_ui(
                            lambda: self.status_var.set(
                                _stage_text(11, "Log to Google Sheet")
                            )
                        )
                        from dubber.sheet_logger import quick_update_from_publish_result

                        formatted_title = self._build_video_sheet_title(
                            approved, video_path
                        )
                        sheet_success, sheet_msg = quick_update_from_publish_result(
                            video_title=formatted_title,
                            publish_results=results,
                            duration=self._get_media_duration_text(video_path),
                            source_lang=self.src_lang_var.get() or "English",
                            target_lang=self.tgt_lang_var.get() or "English",
                            content_format="video",
                        )
                        if sheet_success:
                            log("PUBLISH", f"✅ Google Sheet update: {sheet_msg}")
                        else:
                            log(
                                "PUBLISH", f"⚠️ Google Sheet update skipped: {sheet_msg}"
                            )

                    except ImportError:
                        log("PUBLISH", "⚠️ Google Sheet logger not available")

                try:
                    record_ambiguous_publish_results(video_path, approved, results)
                except Exception as guard_error:
                    log("PUBLISH", f"⚠️ Publish guard update failed: {guard_error}")

                self._queue_ui(lambda: self.run_btn.config(state="normal"))
                self._queue_ui(lambda: self.status_var.set(msg))
                log("PUBLISH", f"✅ Publishing completed: {msg}")
                _safe_done(
                    success=(ok > 0 or unconfirmed > 0), msg=msg, pub_results=results
                )

            except Exception as e:
                log("PUBLISH", f"❌ Publishing error: {e}")
                self._queue_ui(lambda: self.run_btn.config(state="normal"))
                self._queue_ui(lambda: self.status_var.set(f"Publishing failed: {e}"))
                _safe_done(
                    success=False,
                    msg=f"Publishing failed: {e}",
                    pub_results={"error": str(e)},
                )
            finally:
                self._end_publish("dub")

        threading.Thread(target=_publish, daemon=True).start()

    def _done_cb(self, success, msg, pub_results=None):
        self.status_var.set(msg)
        self.run_btn.config(state="normal")
        if pub_results:
            root_error = _extract_error_message(pub_results)
            if root_error:
                print(f"FAIL publish: {root_error}")
            for k, v in pub_results.items():
                if k == "error":
                    continue
                if isinstance(v, dict):
                    status = v.get("status", "unknown")
                    pid = v.get("post_id") or v.get("_id") or "n/a"
                    err = v.get("error") or v.get("error_message")
                    if status in {"likely_live", "duplicate_live"}:
                        print(
                            f"OK   {_display_platform_name(k)}: status={status} note={err or 'likely already live'}"
                        )
                    elif err:
                        print(
                            f"FAIL {_display_platform_name(k)}: status={status} error={err}"
                        )
                    else:
                        print(
                            f"OK   {_display_platform_name(k)}: status={status} id={pid}"
                        )
                else:
                    print(f"OK   {_display_platform_name(k)}: {v}")
        (messagebox.showinfo if success else messagebox.showerror)("Result", msg)

        # Clean up workspace after pipeline completion
        try:
            from dubber.workspace_cleaner import cleanup_temp_files

            cleanup_temp_files("workspace")
            self.status_var.set(f"{msg} (workspace cleaned)")
        except Exception as e:
            self.status_var.set(f"{msg} (cleanup failed: {str(e)})")

    def _update_progress(self, done, total, platform, status):
        """Thread-safe progress update for publishing"""
        if status == "posting":
            self.status_var.set(f"Posting to {_display_platform_name(platform)} ...")
        elif status == "ok":
            self.status_var.set(f"✓ {_display_platform_name(platform)} published")
        elif status == "error":
            self.status_var.set(f"✗ {_display_platform_name(platform)} failed")
        elif status == "timeout":
            self.status_var.set(f"⏱ {_display_platform_name(platform)} timed out")
        elif status == "unconfirmed":
            self.status_var.set(f"⚠ {_display_platform_name(platform)} unconfirmed")
        elif status == "likely_live":
            self.status_var.set(
                f"✓ {_display_platform_name(platform)} likely already live"
            )
        elif status == "skipped":
            self.status_var.set(f"⊘ {_display_platform_name(platform)} skipped")
        elif status == "initializing":
            self.status_var.set("Initializing Zernio SDK...")
        elif status == "uploading_media":
            self.status_var.set("Uploading media to Zernio...")
        elif status == "creating_post":
            self.status_var.set("Creating posts for all platforms...")
        elif status == "completed":
            self.status_var.set("✅ Publishing completed!")
        elif status == "sdk":
            if platform == "sdk":
                self.status_var.set(f"Zernio SDK progress: {done}/{total}")
            else:
                self.status_var.set(f"Processing {platform}...")


def run_cli():
    """
    CLI mode:
    python app.py input.mp4 output.mp4
    """

    if len(sys.argv) < 3:
        print(
            "Usage: python app.py input.mp4 output.mp4 [--voice VOICE_LABEL] [--target-lang LANGUAGE]"
        )
        print(
            'Example: python app.py input.mp4 output.mp4 --voice "Gujarati - Niranjan (M)" --target-lang Gujarati'
        )
        print(
            'Example: python app.py input.mp4 output.mp4 --voice "English - Ryan (M)" --target-lang English'
        )
        sys.exit(1)

    input_video = sys.argv[1]
    output_video = sys.argv[2]

    if not os.path.exists(input_video) and not is_url(input_video):
        print("ERROR: Input file not found")
        sys.exit(1)

    print(f"[CLI] Starting dub for: {input_video}")

    # Parse optional arguments
    import argparse

    parser = argparse.ArgumentParser(description="Dub video to target language")
    parser.add_argument("input", help="Input video file")
    parser.add_argument("output", help="Output video file")
    parser.add_argument(
        "--voice",
        default="English - Ryan (M)",
        help="TTS voice (default: English - Ryan (M))",
    )
    parser.add_argument(
        "--target-lang", default="English", help="Target language (default: English)"
    )
    parser.add_argument(
        "--source-lang", default="English", help="Source language (default: English)"
    )

    args = parser.parse_args()

    # Get voice ID from label
    voice_label = args.voice
    if voice_label in VOICES:
        voice = VOICES[voice_label]
    else:
        # Try to find by partial match
        matching = [v for v in VOICES.keys() if voice_label.lower() in v.lower()]
        if matching:
            voice = VOICES[matching[0]]
            print(f"[CLI] Using voice: {matching[0]}")
        else:
            fallback_label = LANGUAGE_DEFAULT_VOICE.get(args.target_lang, "English - Ryan (M)")
            print(
                f"[CLI] Warning: Voice '{voice_label}' not found, using default for {args.target_lang}: {fallback_label}"
            )
            voice = VOICES.get(fallback_label, VOICES["English - Ryan (M)"])

    model_size = "large"
    src_lang = LANGUAGES.get(args.source_lang, "en")
    tgt_lang = LANGUAGES.get(args.target_lang, "en")

    print(f"[CLI] Voice: {voice}, Source: {src_lang}, Target: {tgt_lang}")

    # Flags
    use_bgm = True
    bgm_volume = 0.35

    # API keys (read from env already handled internally)
    gemini = get_gemini_api_key()
    mistral = get_mistral_api_key()
    zernio = get_zernio_api_key()

    # No publishing in CLI mode
    selected_platforms = []
    publish_now = False
    scheduled_for = None

    def status_cb(msg):
        text = f"[STATUS] {msg}"
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe)

    def caption_ready_cb(**kwargs):
        # Skip review + publishing completely
        pass

    def done_cb(success, msg, pub_results=None):
        print(f"[DONE] {msg}")
        sys.exit(0 if success else 1)

    try:
        run_dub_pipeline(
            video_input=input_video,
            voice=voice,
            model_size=model_size,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            use_bgm=use_bgm,
            bgm_volume=bgm_volume,
            gemini_vision_key=gemini,
            mistral_key=mistral,
            zernio_key=zernio,
            selected_platforms=selected_platforms,
            publish_now=publish_now,
            scheduled_for=scheduled_for,
            auto_teaser=False,
            manual_teaser_path="",
            image_paths=[],
            status_cb=status_cb,
            caption_ready_cb=caption_ready_cb,
            done_cb=done_cb,
            dub_only=True,  # 🔥 IMPORTANT: skip captions/publishing
            progress_cb=lambda p: print(f"[PROGRESS] {p}%"),
            output_path=args.output,
        )

    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli()
    else:
        App().mainloop()
