import os, shutil, threading, tkinter as tk
from tkinter import filedialog, ttk, messagebox

import json
import os
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None
from dubber import (
    transcribe_audio, merge_short_segments, translate_segments,
    generate_tts_audio, build_dubbed_video,
    extract_vision, generate_all_captions,
    generate_teaser, generate_teasers, log,  # Removed legacy publish_to_platforms
    quick_update_from_publish_result,
)
from dubber.utils import PLATFORMS, PLATFORM_LIMITS
from dubber.downloader    import is_url, download_video
from dubber.bgm_separator import separate_background
from dubber.sdk_publisher import publish_to_platforms_sdk
from review_dialog        import ReviewDialog

WORKSPACE   = "workspace"
OUTPUT_FILE = "output.mp4"
ENV_FILE    = ".env"

VOICES = {
    "Gujarati - Niranjan (M)": "gu-IN-NiranjanNeural",
    "Gujarati - Dhwani (F)":   "gu-IN-DhwaniNeural",
    "Hindi - Madhur (M)":      "hi-IN-MadhurNeural",
    "Hindi - Swara (F)":       "hi-IN-SwaraNeural",
    "Tamil - Valluvar (M)":    "ta-IN-ValluvarNeural",
    "Tamil - Pallavi (F)":     "ta-IN-PallaviNeural",
    "Telugu - Mohan (M)":      "te-IN-MohanNeural",
    "Telugu - Shruti (F)":     "te-IN-ShrutiNeural",
    "English - Ryan (M)":      "en-GB-RyanNeural",
    "English - Sonia (F)":     "en-GB-SoniaNeural",
}
WHISPER_MODELS = ["tiny","base","small","medium","large"]
LANGUAGES = {
    "English":"en","Hindi":"hi","Gujarati":"gu",
    "Tamil":"ta","Telugu":"te","Kannada":"kn","Malayalam":"ml","Bengali":"bn",
}

def _load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=",1); env[k.strip()] = v.strip()
    return env

def _save_env(data):
    e = _load_env(); e.update(data)
    with open(ENV_FILE,"w") as f:
        for k,v in e.items(): f.write(f"{k}={v}\n")

def _count_successful_results(results):
    """Count successful platform results, handling error-shaped responses."""
    if not isinstance(results, dict):
        return 0
    if "error" in results and len(results) == 1:
        return 0
    return sum(
        1 for v in results.values()
        if isinstance(v, dict) and "error" not in v and v.get("status", "ok") != "error"
    )


def run_dub_pipeline(video_input, voice, model_size, src_lang, tgt_lang,
                     use_bgm, bgm_volume, gemini_vision_key, mistral_key, zernio_key,
                     selected_platforms, publish_now, scheduled_for,
                     auto_teaser, manual_teaser_path, image_paths,
                     status_cb, caption_ready_cb, done_cb):
    try:
        shutil.rmtree(WORKSPACE, ignore_errors=True); os.makedirs(WORKSPACE, exist_ok=True)

        if is_url(video_input):
            status_cb("Downloading video ...")
            video_path = download_video(video_input, WORKSPACE)
        else:
            video_path = video_input
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Not found: {video_path}")

        bgm_path = None
        if use_bgm:
            status_cb("Separating background music ...")
            bgm_path = separate_background(video_path, WORKSPACE)

        status_cb("Stage 1/5 - Transcribing ...")
        segs = transcribe_audio(video_path, WORKSPACE, model_size, src_lang)
        status_cb("Stage 2/5 - Merging segments ...")
        segs = merge_short_segments(segs)
        status_cb("Stage 3/5 - Translating ...")
        segs = translate_segments(segs, tgt_lang, WORKSPACE)
        status_cb("Stage 4/5 - Generating TTS ...")
        segs = generate_tts_audio(segs, voice=voice, output_dir=WORKSPACE)
        status_cb("Stage 5/5 - Building video ...")
        build_dubbed_video(video_path=video_path, segments=segs,
                           output_path=OUTPUT_FILE, bgm_path=bgm_path,
                           bgm_volume=bgm_volume, output_dir=WORKSPACE)

        status_cb("Extracting content intelligence ...")
        vision   = extract_vision(segs, gemini_vision_key, WORKSPACE)
        status_cb("Generating captions ...")
        captions = generate_all_captions(vision, mistral_key, WORKSPACE, segments=segs)

        teaser_path  = None
        teaser_paths = {}
        if manual_teaser_path and os.path.exists(manual_teaser_path):
            teaser_path  = manual_teaser_path
            teaser_paths = {p: manual_teaser_path for p in PLATFORMS}
        elif auto_teaser:
            status_cb("Generating per-platform teaser clips ...")
            teaser_paths = generate_teasers(OUTPUT_FILE, segs, captions, WORKSPACE)
            teaser_path  = teaser_paths.get("instagram")

        status_cb("Waiting for caption review ...")
        caption_ready_cb(
            captions=captions, teaser_path=teaser_path,
            teaser_paths=teaser_paths,
            video_path=OUTPUT_FILE, zernio_key=zernio_key,
            selected_platforms=selected_platforms,
            publish_now=publish_now, scheduled_for=scheduled_for,
            image_paths=image_paths, done_cb=done_cb,
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        done_cb(success=False, msg=str(e), pub_results={})


def run_publish_only(image_paths, teaser_path, topic_hint,
                     gemini_vision_key, mistral_key, zernio_key,
                     selected_platforms, publish_now, scheduled_for,
                     status_cb, caption_ready_cb, done_cb):
    try:
        os.makedirs(WORKSPACE, exist_ok=True)

        if mistral_key and topic_hint.strip():
            status_cb("Generating captions from topic hint ...")
            vision = {
                "main_topic":        topic_hint.strip(),
                "core_conflict":     topic_hint.strip(),
                "provocative_angle": topic_hint.strip(),
                "festival":          "None",
                "location":          "None",
                "date":              "None",
                "theme":             "teaching",
            }
            captions = generate_all_captions(vision, mistral_key, WORKSPACE)
        else:
            status_cb("Opening caption review for manual entry ...")
            captions = {p: {"caption":""} for p in PLATFORMS}
            for p in PLATFORMS:
                if p == "youtube": captions[p]["title"] = ""

        status_cb("Waiting for caption review ...")
        primary = image_paths[0] if image_paths else (teaser_path or "")
        caption_ready_cb(
            captions=captions, teaser_path=teaser_path,
            video_path=primary, zernio_key=zernio_key,
            selected_platforms=selected_platforms,
            publish_now=publish_now, scheduled_for=scheduled_for,
            image_paths=image_paths[1:] if len(image_paths) > 1 else [],
            done_cb=done_cb,
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        done_cb(success=False, msg=str(e), pub_results={})


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Dubber v2.0")
        self.geometry("920x740")
        self.minsize(840, 660)
        self.resizable(True, True)
        self._env         = _load_env()
        self._image_paths = []
        self._header_photo = None
        self._init_theme()
        self._build_ui()

    def _init_theme(self):
        self._colors = {
            "bg": "#F9F5EF",         # Sandstone BG
            "panel": "#F4EFE6",      # Surface
            "input": "#EDE6D8",      # Surface 2
            "muted": "#6B5740",      # Warm Muted
            "text": "#1E1209",       # Deep Ink
            "border": "#D5C8B0",     # Stone Border
            "primary": "#7B1F1F",    # Kaavi
            "primary_dark": "#5A1515",  # Kaavi Dark
            "accent": "#C8860A",     # Sacred Gold
            "accent_bright": "#E8A020", # Gold Bright
            "success": "#2C5F2E",    # Dharma Green
            "danger": "#E8700A",     # Saffron
        }
        self.configure(bg=self._colors["bg"])

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Modern.TNotebook", background=self._colors["bg"], borderwidth=0)
        style.configure(
            "Modern.TNotebook.Tab",
            padding=(18, 8),
            font=("Segoe UI", 10, "bold"),
            background=self._colors["primary_dark"],
            foreground="white",
        )
        style.map(
            "Modern.TNotebook.Tab",
            background=[("selected", self._colors["primary"]), ("!selected", self._colors["primary_dark"])],
            foreground=[("selected", "white"), ("!selected", "white")],
        )
        style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor=self._colors["panel"],
            background=self._colors["accent"],
            bordercolor=self._colors["border"],
            lightcolor=self._colors["accent"],
            darkcolor=self._colors["accent"],
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
            button.configure(bg=hover)

        def _on_leave(_event):
            button.configure(bg=normal)

        def _on_press(_event):
            button.configure(bg=pressed)

        def _on_release(_event):
            inside = button.winfo_containing(button.winfo_pointerx(), button.winfo_pointery()) == button
            button.configure(bg=hover if inside else normal)

        button.bind("<Enter>", _on_enter)
        button.bind("<Leave>", _on_leave)
        button.bind("<ButtonPress-1>", _on_press)
        button.bind("<ButtonRelease-1>", _on_release)

    def _fit_caption_for_platform(self, platform, caption):
        """Trim caption to platform character limits when needed."""
        limit = PLATFORM_LIMITS.get(platform)
        if limit is None:
            return caption, False, None
        text = str(caption or "").strip()
        if len(text) <= limit:
            return text, False, limit
        ellipsis = "..."
        cut = max(0, limit - len(ellipsis))
        trimmed = text[:cut].rstrip() + ellipsis
        return trimmed, True, limit

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

    def _build_video_sheet_title(self, approved_captions, video_path):
        """Return `Gujarati Title (English Title)` when available."""
        fallback = os.path.splitext(os.path.basename(video_path))[0]
        youtube = approved_captions.get("youtube", {}) if isinstance(approved_captions, dict) else {}
        gujarati_title = ""
        if isinstance(youtube, dict):
            gujarati_title = (youtube.get("title") or "").strip()
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

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

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

        tk.Label(self.t_dub, text="1) Source Input", font=("Segoe UI Semibold", 11)).grid(row=0, column=0, sticky="w", **pad)
        tk.Label(self.t_dub, text="Video / URL:", font=("Segoe UI", 10)).grid(row=1,column=0,sticky="w",**pad)
        self.video_var = tk.StringVar()
        tk.Entry(self.t_dub, textvariable=self.video_var, width=54, relief="solid", bd=1).grid(row=1,column=1,**pad)
        tk.Button(self.t_dub, text="Browse", command=self._browse_video, width=10, bg=self._colors["input"], fg=self._colors["text"], relief="solid", bd=1).grid(row=1,column=2,**pad)

        tk.Label(self.t_dub, text="2) Language & Voice", font=("Segoe UI Semibold", 11)).grid(row=2, column=0, sticky="w", **pad)
        tk.Label(self.t_dub, text="Voice:", font=("Segoe UI", 10)).grid(row=3,column=0,sticky="w",**pad)
        self.voice_var = tk.StringVar(value=list(VOICES.keys())[0])
        ttk.Combobox(self.t_dub, textvariable=self.voice_var, values=list(VOICES.keys()),
                     width=46, state="readonly").grid(row=3,column=1,columnspan=2,sticky="ew",**pad)

        tk.Label(self.t_dub, text="Whisper model:", font=("Segoe UI", 10)).grid(row=4,column=0,sticky="w",**pad)
        self.model_var = tk.StringVar(value="medium")
        ttk.Combobox(self.t_dub, textvariable=self.model_var, values=WHISPER_MODELS,
                     width=16, state="readonly").grid(row=4,column=1,sticky="w",**pad)

        tk.Label(self.t_dub, text="Source lang:", font=("Segoe UI", 10)).grid(row=5,column=0,sticky="w",**pad)
        self.src_lang_var = tk.StringVar(value="English")
        ttk.Combobox(self.t_dub, textvariable=self.src_lang_var,
                     values=list(LANGUAGES.keys()), width=16,
                     state="readonly").grid(row=5,column=1,sticky="w",**pad)

        tk.Label(self.t_dub, text="Target lang:", font=("Segoe UI", 10)).grid(row=6,column=0,sticky="w",**pad)
        self.tgt_lang_var = tk.StringVar(value="Gujarati")
        ttk.Combobox(self.t_dub, textvariable=self.tgt_lang_var,
                     values=list(LANGUAGES.keys()), width=16,
                     state="readonly").grid(row=6,column=1,sticky="w",**pad)

        ttk.Separator(self.t_dub,orient="horizontal").grid(row=7,column=0,columnspan=3,sticky="ew",pady=8)
        tk.Label(self.t_dub, text="3) Audio Blend & Platforms", font=("Segoe UI Semibold", 11)).grid(row=8, column=0, sticky="w", **pad)
        self.bgm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.t_dub, text="Preserve background music (Demucs)",
                       variable=self.bgm_var, command=self._toggle_bgm
                       ).grid(row=9,column=0,columnspan=2,sticky="w",**pad)
        tk.Label(self.t_dub, text="Music volume:", font=("Segoe UI", 10)).grid(row=10,column=0,sticky="w",**pad)
        self.bgm_vol_var = tk.DoubleVar(value=0.35)
        self.bgm_scale = tk.Scale(self.t_dub, variable=self.bgm_vol_var,
                                  from_=0.0, to=1.0, resolution=0.05,
                                  orient="horizontal", length=220,
                                  bg=self._colors["panel"], fg=self._colors["text"], highlightthickness=0)
        self.bgm_scale.grid(row=10,column=1,sticky="w",**pad)

        tk.Label(self.t_dub, text="Platforms to publish:", font=("Segoe UI", 10)).grid(row=11,column=0,sticky="w",**pad)
        self._plat_vars = {}
        pf = tk.Frame(self.t_dub, bg=self._colors["panel"]); pf.grid(row=11,column=1,columnspan=2,sticky="w")
        for i,p in enumerate(PLATFORMS):
            v = tk.BooleanVar(value=True); self._plat_vars[p] = v
            tk.Checkbutton(pf,text=p.capitalize(),variable=v, font=("Segoe UI", 9)).grid(row=i//4,column=i%4,sticky="w",padx=6)
        
        ttk.Separator(self.t_dub,orient="horizontal").grid(row=12,column=0,columnspan=3,sticky="ew",pady=8)
        self.dub_publish_now_var = tk.BooleanVar(value=True)
        tk.Radiobutton(self.t_dub, text="Publish immediately",
                       variable=self.dub_publish_now_var, value=True, font=("Segoe UI", 9)).grid(row=13,column=0,columnspan=2,sticky="w",**pad)

        ttk.Separator(self.t_dub,orient="horizontal").grid(row=14,column=0,columnspan=3,sticky="ew",pady=8)
        tk.Label(self.t_dub, text="Pipeline activity", font=("Segoe UI Semibold", 11)).grid(row=15,column=0,sticky="w",**pad)
        self.dub_results = tk.Text(self.t_dub, width=84, height=8, font=("Consolas",9))
        self.dub_results.grid(row=16,column=0,columnspan=3,padx=12,pady=(0,8), sticky="nsew")
        self.t_dub.grid_rowconfigure(16, weight=1)
        self._style_text_area(self.dub_results)

        self.t_media_tab = tk.Frame(self.nb, bg=self._colors["panel"], padx=0, pady=0)
        self.nb.add(self.t_media_tab, text="  Flyer / Image  ")
        self.t_media = self._create_scrollable_tab(self.t_media_tab)
        self.t_media.configure(padx=16, pady=12)
        self.t_media.grid_columnconfigure(1, weight=1)

        tk.Label(self.t_media, text="Flyer/Image Processing", 
                 font=("Segoe UI Semibold",12)).grid(row=0,column=0,columnspan=3,sticky="w",**pad)
        tk.Label(self.t_media, text="Upload flyers/posters to extract text and generate Gujarati content",
                 fg=self._colors["muted"], font=("Segoe UI",9)).grid(row=1,column=0,columnspan=3,sticky="w",padx=12,pady=(0,6))

        ttk.Separator(self.t_media,orient="horizontal").grid(row=2,column=0,columnspan=3,sticky="ew",pady=8)
        
        tk.Label(self.t_media, text="Select Flyer/Images:", font=("Segoe UI Semibold",10)).grid(row=3,column=0,sticky="w",**pad)
        self.flyer_var = tk.StringVar()
        tk.Entry(self.t_media, textvariable=self.flyer_var, width=54, relief="solid", bd=1).grid(row=3,column=1,**pad)
        tk.Button(self.t_media, text="Browse", command=self._browse_flyer, width=10, bg=self._colors["input"], fg=self._colors["text"], relief="solid", bd=1).grid(row=3,column=2,**pad)
        
        self.flyer_paths = []
        self.flyer_count_label = tk.Label(self.t_media, text="", fg=self._colors["muted"], font=("Segoe UI",8))
        self.flyer_count_label.grid(row=4,column=0,columnspan=3,sticky="w",padx=12)
        
        ttk.Separator(self.t_media,orient="horizontal").grid(row=5,column=0,columnspan=3,sticky="ew",pady=8)
        tk.Label(self.t_media, text="Processing Options:", font=("Segoe UI Semibold",10)).grid(row=6,column=0,sticky="w",**pad)
        
        self.extract_text_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.t_media, text="Extract text from flyer/image",
                       variable=self.extract_text_var, font=("Segoe UI", 9)).grid(row=7,column=0,columnspan=3,sticky="w",padx=12)
        
        self.generate_captions_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.t_media, text="Generate Gujarati captions",
                       variable=self.generate_captions_var, font=("Segoe UI", 9)).grid(row=8,column=0,columnspan=3,sticky="w",padx=12)
        
        self.generate_teaser_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.t_media, text="Create teaser content",
                       variable=self.generate_teaser_var, font=("Segoe UI", 9)).grid(row=9,column=0,columnspan=3,sticky="w",padx=12)
        
        ttk.Separator(self.t_media,orient="horizontal").grid(row=10,column=0,columnspan=3,sticky="ew",pady=8)
        bf = tk.Frame(self.t_media, bg=self._colors["panel"]); bf.grid(row=11,column=0,columnspan=3,sticky="w",padx=12)
        tk.Button(bf,text="Clear Selection",command=self._clear_flyer, bg=self._colors["input"], fg=self._colors["text"], relief="solid", bd=1).pack(side="left",padx=4)
        
        tk.Label(self.t_media, text="Processing activity", font=("Segoe UI Semibold",10)).grid(row=12,column=0,sticky="w",**pad)
        self.flyer_results = tk.Text(self.t_media, width=84, height=8, font=("Consolas",9))
        self.flyer_results.grid(row=13,column=0,columnspan=3,padx=12,pady=(0,8), sticky="nsew")
        self.t_media.grid_rowconfigure(13, weight=1)
        self._style_text_area(self.flyer_results)
        
        ttk.Separator(self.t_media,orient="horizontal").grid(row=14,column=0,columnspan=3,sticky="ew",pady=8)
        tk.Label(self.t_media, text="Platforms to Publish:", font=("Segoe UI Semibold",10)).grid(row=15,column=0,sticky="w",**pad)
        self._flyer_plat_vars = {}
        pf = tk.Frame(self.t_media, bg=self._colors["panel"]); pf.grid(row=15,column=1,columnspan=2,sticky="w")
        for i,p in enumerate(PLATFORMS):
            if p not in ["youtube", "tiktok"]:
                v = tk.BooleanVar(value=True); self._flyer_plat_vars[p] = v
                tk.Checkbutton(pf,text=p.capitalize(),variable=v, font=("Segoe UI", 9)).grid(row=i//4,column=i%4,sticky="w",padx=6)
        
        ttk.Separator(self.t_media,orient="horizontal").grid(row=16,column=0,columnspan=3,sticky="ew",pady=8)
        self.flyer_publish_now_var = tk.BooleanVar(value=True)
        tk.Radiobutton(self.t_media, text="Publish immediately",
                       variable=self.flyer_publish_now_var, value=True, font=("Segoe UI", 9)).grid(row=17,column=0,columnspan=2,sticky="w",**pad)

        # Bottom action bar
        bot = tk.Frame(self, bg=self._colors["panel"], relief="solid", bd=1, padx=10, pady=8)
        bot.pack(side="bottom", fill="x", padx=16, pady=(6, 10))

        self.cleanup_btn = tk.Button(
            bot, text="Clean Workspace", width=14,
            bg=self._colors["danger"], fg="white",
            font=("Segoe UI Semibold", 9), command=self._manual_cleanup,
            relief="flat", bd=0, padx=10, pady=6
        )
        self.cleanup_btn.pack(side="left", padx=6)

        center_frame = tk.Frame(bot, bg=self._colors["panel"])
        center_frame.pack(side="left", expand=True, fill="x", padx=12)

        self.process_flyer_btn = tk.Button(
            center_frame, text="Process Flyer", command=self._process_flyer,
            bg=self._colors["accent"], fg="white", width=14,
            font=("Segoe UI Semibold", 9), relief="flat", bd=0, padx=10, pady=6
        )
        self.process_flyer_btn.pack(side="left", padx=4)

        self.publish_flyer_btn = tk.Button(
            center_frame, text="Publish Content", command=self._publish_flyer_content,
            bg=self._colors["success"], fg="white", width=14,
            font=("Segoe UI Semibold", 9), relief="flat", bd=0, padx=10, pady=6
        )
        self.publish_flyer_btn.pack(side="left", padx=4)

        self.run_btn = tk.Button(
            bot, text="Run Dub Pipeline", width=16,
            bg=self._colors["primary"], fg="white",
            font=("Segoe UI Semibold", 9), command=self._run,
            relief="flat", bd=0, padx=10, pady=6
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

        self.progress = ttk.Progressbar(self, mode="indeterminate", style="Modern.Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=16, pady=(0, 6))

        status_frame = tk.Frame(self, bg=self._colors["panel"], relief="solid", bd=1)
        self.status_var = tk.StringVar(value="Ready.")
        status_label = tk.Label(
            status_frame, textvariable=self.status_var, fg=self._colors["text"],
            bg=self._colors["panel"], font=("Segoe UI", 9), anchor="w"
        )
        status_label.pack(side="left", padx=8, pady=5, fill="x", expand=True)
        status_frame.pack(side="bottom", fill="x", padx=16, pady=(0, 12))

        # Store flyer path
        self.flyer_path = ""

        # Initialize API key variables (hidden from GUI)
        self.gemini_vision_key_var = tk.StringVar(value=self._env.get("GEMINI_VISION_KEY",""))
        self.mistral_key_var = tk.StringVar(value=self._env.get("MISTRAL_API_KEY",""))
        self.zernio_key_var = tk.StringVar(value=self._env.get("ZERNIO_API_KEY",""))
        
        # Initialize missing variables from Publish Only tab
        self.topic_var = tk.StringVar()
        self.pub_teaser_var = tk.StringVar()
        self._image_paths = []
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

    def _toggle_bgm(self):
        self.bgm_scale.config(state="normal" if self.bgm_var.get() else "disabled")

    
    def _clear_flyer(self):
        """Clear flyer selection and results"""
        self.flyer_var.set("")
        self.flyer_path = ""
        self.flyer_paths = []  # Clear multiple images
        self.flyer_count_label.config(text="")
        self.flyer_results.delete(1.0, tk.END)
    
    def _clear_dub_results(self):
            """Clear dub results"""
            self.dub_results.delete(1.0, tk.END)
    
    def _update_dub_results(self, message):
            """Update dub results with new message"""
            self.dub_results.insert(tk.END, f"{message}\n")
            self.dub_results.see(tk.END)  # Auto-scroll to bottom
    
    def _browse_video(self):
        """Browse for video file"""
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("All files", "*.*")
            ]
        )
        if file_path:
            self.video_var.set(file_path)
    
    def _browse_flyer(self):
        """Browse for flyer/image files (multiple selection)"""
        file_paths = filedialog.askopenfilenames(
            title="Select Flyer/Images (Ctrl+Click for multiple)",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.gif *.bmp *.webp"),
                ("All files", "*.*")
            ]
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
                    preview += f" +{len(file_paths)-3} more"
                self.flyer_count_label.config(text=preview)
            
            # Store single path for compatibility
            self.flyer_path = file_paths[0]
    
    def _process_flyer(self):
        """Process flyer to extract text and generate content"""
        if not self.flyer_path:
            messagebox.showerror("Error", "Please select a flyer/image file first")
            return
        
        if not os.path.exists(self.flyer_path):
            messagebox.showerror("Error", "File not found")
            return
        
        try:
            self.flyer_results.delete(1.0, tk.END)
            self.flyer_results.insert(tk.END, "🔄 Processing flyer...\n\n")
            
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
                    extracted_text = extract_text_from_image(self.flyer_path, gemini_key)
                    self.flyer_results.insert(tk.END, f"✅ Extracted {len(extracted_text)} characters\n")
                    self.flyer_results.insert(tk.END, f"Text: {extracted_text[:200]}{'...' if len(extracted_text) > 200 else ''}\n\n")
                except Exception as e:
                    self.flyer_results.insert(tk.END, f"❌ Text extraction failed: {str(e)}\n\n")
            
            # Generate Gujarati captions
            if self.generate_captions_var.get() and extracted_text:
                self.flyer_results.insert(tk.END, "🎨 Generating Gujarati captions...\n")
                try:
                    from dubber.image_processor import generate_gujarati_captions
                    captions = generate_gujarati_captions(extracted_text, gemini_key)
                    if isinstance(captions, dict) and "error" not in captions:
                        self.flyer_results.insert(tk.END, "✅ Generated captions for all platforms\n")
                        for platform, caption in captions.items():
                            self.flyer_results.insert(tk.END, f"  {platform.title()}: {caption[:100]}{'...' if len(caption) > 100 else ''}\n")
                    else:
                        self.flyer_results.insert(tk.END, f"❌ Caption generation failed: {captions}\n")
                    self.flyer_results.insert(tk.END, "\n")
                except Exception as e:
                    self.flyer_results.insert(tk.END, f"❌ Caption generation failed: {str(e)}\n\n")
            
            # Generate teaser content
            if self.generate_teaser_var.get() and extracted_text:
                self.flyer_results.insert(tk.END, "🎬 Creating teaser content...\n")
                try:
                    from dubber.image_processor import generate_teaser_content
                    teaser = generate_teaser_content(extracted_text, captions, gemini_key)
                    if isinstance(teaser, dict) and "error" not in teaser:
                        self.flyer_results.insert(tk.END, "✅ Generated teaser content\n")
                        for key, value in teaser.items():
                            self.flyer_results.insert(tk.END, f"  {key.replace('_', ' ').title()}: {value}\n")
                    else:
                        self.flyer_results.insert(tk.END, f"❌ Teaser generation failed: {teaser}\n")
                    self.flyer_results.insert(tk.END, "\n")
                except Exception as e:
                    self.flyer_results.insert(tk.END, f"❌ Teaser generation failed: {str(e)}\n\n")
            
            self.flyer_results.insert(tk.END, "🎉 Processing complete!\n")
            
            # Save results to workspace
            if extracted_text or captions or teaser:
                workspace_dir = "workspace"
                os.makedirs(workspace_dir, exist_ok=True)
                
                # Save extracted text
                if extracted_text:
                    with open(os.path.join(workspace_dir, "flyer_text.txt"), "w", encoding="utf-8") as f:
                        f.write(extracted_text)
                
                # Save captions
                if captions and isinstance(captions, dict):
                    with open(os.path.join(workspace_dir, "flyer_captions.json"), "w", encoding="utf-8") as f:
                        json.dump(captions, f, ensure_ascii=False, indent=2)
                
                # Save teaser
                if teaser and isinstance(teaser, dict):
                    with open(os.path.join(workspace_dir, "flyer_teaser.json"), "w", encoding="utf-8") as f:
                        json.dump(teaser, f, ensure_ascii=False, indent=2)
                
                self.flyer_results.insert(tk.END, f"💾 Results saved to {workspace_dir}/ folder\n")
                
                # Auto-cleanup after 30 seconds if enabled
                if hasattr(self, 'auto_cleanup_var') and self.auto_cleanup_var.get():
                    self.flyer_results.insert(tk.END, f"⏰ Auto-cleanup in 30 seconds...\n")
                    self.after(30000, lambda: self._delayed_cleanup(workspace_dir))
                else:
                    self.flyer_results.insert(tk.END, f"💡 Files will remain - use '🧹 Clean' button when ready\n")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process flyer: {str(e)}")
            self.flyer_results.insert(tk.END, f"❌ Error: {str(e)}\n")

    def _publish_flyer_content(self):
        """Publish the generated flyer content"""
        try:
            # Check if captions exist
            captions_file = os.path.join("workspace", "flyer_captions.json")
            if not os.path.exists(captions_file):
                messagebox.showerror("No Content", "Please process the flyer first to generate captions!")
                return
            
            # Load captions
            with open(captions_file, "r", encoding="utf-8") as f:
                captions = json.load(f)
            
            # Check if flyer image exists
            if not self.flyer_path or not os.path.exists(self.flyer_path):
                messagebox.showerror("No Image", "Please select a flyer image first!")
                return
            
            # Get selected platforms from flyer tab (already excludes video-only platforms)
            selected = [p for p,v in self._flyer_plat_vars.items() if v.get()]
            print(f"DEBUG: Selected flyer platforms: {selected}")
            
            if not selected:
                messagebox.showwarning("No Platforms", 
                    "Please select at least one image-compatible platform (Instagram, Facebook, X, Threads, Bluesky)!\n\nNote: YouTube and TikTok don't support image publishing.")
                return
            
            # Get API keys
            zernio_key = self.zernio_key_var.get().strip()
            if not zernio_key:
                messagebox.showerror("No API Key", "Please enter Zernio API key in AI & Publish tab!")
                return
            
            # Prepare captions for publishing (needed for both live and test mode)
            publish_captions = {}
            adjusted_platforms = []
            for platform in selected:
                raw_caption = captions.get(platform)
                if isinstance(raw_caption, dict):
                    raw_caption = raw_caption.get("caption", "")
                if raw_caption is None:
                    raw_caption = f"Check out this content from KAILASA! #KAILASA #Nithyananda"
                fitted_caption, adjusted, limit = self._fit_caption_for_platform(platform, raw_caption)
                if adjusted:
                    adjusted_platforms.append((platform, len(str(raw_caption)), limit))
                if platform in captions:
                    publish_captions[platform] = {
                        "caption": fitted_caption
                    }
                else:
                    publish_captions[platform] = {
                        "caption": fitted_caption
                    }

            if adjusted_platforms:
                self.flyer_results.insert(tk.END, "✂️ Caption length adjusted for platform limits:\n")
                for platform, original_len, limit in adjusted_platforms:
                    self.flyer_results.insert(
                        tk.END,
                        f"  - {platform.title()}: {original_len} → {limit} chars\n"
                    )
                self.flyer_results.insert(tk.END, "\n")
                self.flyer_results.see(tk.END)
            
            # Show confirmation dialog with test option
            result = messagebox.askyesno("Confirm Publish", 
                f"Publish flyer to {len(selected)} platform(s):\n{', '.join(selected)}\n\nImage: {os.path.basename(self.flyer_path)}\n\nClick YES to publish, NO to test mode (no actual posting)")
            if not result:  # User clicked NO = test mode
                # Test mode - show what would be published without actually posting
                self._test_flyer_publish(selected, publish_captions)
                return
            
            # Start publishing
            self.status_var.set("Publishing flyer...")
            self.progress.start(12)
            publish_now_flag = bool(self.flyer_publish_now_var.get())
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
                        progress_cb=lambda done, total, platform, status: self._queue_ui(
                            lambda: self._update_progress(done, total, platform, status)
                        ),
                        fallback_files={
                            "main_image": primary_flyer,
                            "additional_images": additional_flyers
                        }  # Pass all images for upload
                    )
                    
                    # Count successful publishes correctly (ignore top-level {"error": "..."} payloads)
                    successful = _count_successful_results(results)
                    
                    self._queue_ui(lambda: self._flyer_publish_done(successful, len(selected), results))
                    
                except Exception as e:
                    self._queue_ui(lambda: self._flyer_publish_done(0, 1, {"error": str(e)}))
            
            threading.Thread(target=_publish_thread, daemon=True).start()
            
        except Exception as e:
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
        
        messagebox.showinfo("Test Mode Complete", "Test mode complete - no actual posts were made.\nCheck the Results section for details.")
        self.status_var.set("Test mode completed")

    def _flyer_publish_done(self, successful, total, results):
        """Handle flyer publishing completion"""
        self.progress.stop()
        self.flyer_results.insert(tk.END, "\n📊 Publish Results:\n")
        self.flyer_results.insert(tk.END, "=" * 40 + "\n")
        failure_lines = []
        success_lines = []
        for platform, result in results.items():
            if isinstance(result, dict):
                status = str(result.get("status", "")).lower()
                post_id = result.get("post_id") or result.get("_id") or "n/a"
                if status == "ok":
                    success_lines.append(f"✅ {platform}: {post_id}")
                else:
                    err_msg = result.get("error") or result.get("error_message") or "Unknown error"
                    failure_lines.append(f"❌ {platform}: {err_msg}")
            elif isinstance(result, bool):
                if result:
                    success_lines.append(f"✅ {platform}: success")
                else:
                    failure_lines.append(f"❌ {platform}: skipped")
            else:
                failure_lines.append(f"❌ {platform}: unexpected result format")

        for line in success_lines + failure_lines:
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
                messagebox.showinfo("Success", f"Successfully published to {successful} platform(s)!")
            
            # Log to Google Sheet after successful flyer publish
            try:
                from dubber.sheet_logger import quick_update_from_publish_result
                
                # Get flyer title for sheet
                formatted_title = ""
                try:
                    # Use flyer filename as title
                    flyer_title = os.path.basename(self.flyer_path)
                    # Remove extension
                    title_without_ext = os.path.splitext(flyer_title)[0]
                    
                    # Try to get Gujarati title from flyer captions
                    captions_file = os.path.join("workspace", "flyer_captions.json")
                    if os.path.exists(captions_file):
                        with open(captions_file, "r", encoding="utf-8") as f:
                            captions = json.load(f)
                        
                        # Get Gujarati title from any platform (YouTube might have title)
                        gujarati_title = ""
                        for platform, data in captions.items():
                            if isinstance(data, dict) and data.get("title"):
                                gujarati_title = data["title"]
                                break
                        
                        if gujarati_title:
                            # Format as "Gujarati (English)"
                            formatted_title = f"{gujarati_title} ({title_without_ext})"
                            print(f"[SHEET] Using formatted flyer title: {formatted_title}")
                        else:
                            formatted_title = title_without_ext
                    else:
                        formatted_title = title_without_ext
                        
                except Exception as e:
                    print(f"[SHEET] Error getting flyer title: {e}")
                    formatted_title = os.path.basename(self.flyer_path)
                
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
                
        else:
            self.status_var.set("Publishing failed")
            error_msg = "\n".join(failure_lines[:6]) if failure_lines else "Publishing failed. Check API keys and try again."
            messagebox.showerror("Failed", error_msg)
        
        # Log results
        for platform, result in results.items():
            if isinstance(result, dict) and "error" in result:
                print(f'FAIL {platform}: {result["error"]}')
            elif isinstance(result, bool):
                # Handle case where result is a boolean (from skip logic)
                status = "skipped" if not result else "success"
                print(f'OK   {platform}: {status}')
            else:
                # Normal case - result is a dict with post info
                post_id = result.get("_id", "success") if isinstance(result, dict) else "success"
                print(f'OK   {platform}: {post_id}')

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
            messagebox.showerror("Cleanup Failed", f"Failed to clean workspace: {str(e)}")

    def _save_keys(self):
        to_save = {}
        if self.gemini_vision_key_var.get().strip():
            to_save["GEMINI_VISION_KEY"] = self.gemini_vision_key_var.get().strip()
        if self.mistral_key_var.get().strip():
            to_save["MISTRAL_API_KEY"] = self.mistral_key_var.get().strip()
        if self.zernio_key_var.get().strip():
            to_save["ZERNIO_API_KEY"] = self.zernio_key_var.get().strip()
        if to_save:
            _save_env(to_save)
        self.status_var.set("Keys saved.")

    def _run(self):
        # Always run dub pipeline since mode selection is removed
        video = self.video_var.get().strip()
        if not video:
            messagebox.showwarning("No input","Paste a URL or browse for a video.")
            return
        self.run_btn.config(state="disabled")
        self._clear_dub_results()  # Clear previous results
        self.dub_results.insert(tk.END, "🔄 Starting dub pipeline...\n\n")
        self.progress.start(12); self.status_var.set("Starting dub pipeline ...")
        
        selected = [p for p,v in self._plat_vars.items() if v.get()]
        # No scheduling implemented yet - always publish immediately
        sched = None
        gemini_vision = self.gemini_vision_key_var.get().strip()
        mistral = self.mistral_key_var.get().strip()
        zernio = self.zernio_key_var.get().strip()
        to_save = {}
        if gemini_vision: to_save["GEMINI_VISION_KEY"] = gemini_vision
        if mistral:       to_save["MISTRAL_API_KEY"]   = mistral
        if zernio:        to_save["ZERNIO_API_KEY"]     = zernio
        if to_save:       _save_env(to_save)
        
        # No manual teaser needed for dub pipeline - use auto generation
        manual_teaser = ""
        
        # Create custom status callback for dub results
        def dub_status_callback(message):
            self.after(0, lambda: self._update_dub_results(message))
        
        # Test callback immediately
        dub_status_callback("🔄 Initializing dub pipeline...")

        def safe_done_callback(success, msg, pub_results=None):
            self.after(0, lambda: self._done_cb(success, msg, pub_results))
        
        threading.Thread(target=run_dub_pipeline, args=(
            video, VOICES[self.voice_var.get()], self.model_var.get(),
            LANGUAGES[self.src_lang_var.get()], LANGUAGES[self.tgt_lang_var.get()],
            self.bgm_var.get(), self.bgm_vol_var.get(),
            gemini_vision, mistral, zernio, selected,
            self.dub_publish_now_var.get(), sched,
            True, manual_teaser,  # auto_teaser=True, manual_teaser=""
            list(self._image_paths),
            dub_status_callback, self._caption_ready_cb, safe_done_callback,
        ), daemon=True).start()

    def _caption_ready_cb(self, **kwargs):
        self.after(0, lambda: self._show_review(**kwargs))

    def _show_review(self, captions, teaser_path, video_path, zernio_key,
                     selected_platforms, publish_now, scheduled_for,
                     image_paths, done_cb, teaser_paths=None):
        self.progress.stop()
        self.status_var.set("Review captions — edit if needed, then approve.")
        
        # Show review dialog (simplified without parallel uploads for now)
        dlg = ReviewDialog(self, captions, upload_manager=None)
        if dlg.result is None:
            self.run_btn.config(state="normal")
            self.status_var.set("Publishing cancelled."); return
        approved = dlg.result

        def _safe_done(success, msg, pub_results=None):
            if done_cb:
                if not self._queue_ui(lambda: done_cb(success=success, msg=msg, pub_results=pub_results)):
                    try:
                        done_cb(success=success, msg=msg, pub_results=pub_results)
                    except Exception:
                        pass

        self.progress.start(12); self.status_var.set("Publishing ...")

        # Thread-safe progress callback for status bar updates
        def _thread_safe_progress(done, total, platform, status):
            """Thread-safe progress update for status bar"""
            self._queue_ui(lambda: self._update_progress(done, total, platform, status))

        def _publish():
            try:
                results = publish_to_platforms_sdk(
                    api_key=zernio_key,
                    video_path=video_path,
                    captions=approved,
                    platforms=selected_platforms,
                    scheduled_for=scheduled_for if not publish_now else None,
                    publish_now=publish_now,
                    teaser_path=teaser_path,
                    teaser_paths=teaser_paths,
                    image_paths=image_paths,
                    output_dir=WORKSPACE,
                    progress_cb=_thread_safe_progress,
                    fallback_files={"main_video": video_path}  # Pass video for upload
                )
                
                ok = _count_successful_results(results)
                msg = f"Published {ok} post(s)." if ok else "All posts failed — check log."
                
                # Log to Google Sheet after successful publish
                if ok > 0:
                    try:
                        from dubber.sheet_logger import quick_update_from_publish_result
                        formatted_title = self._build_video_sheet_title(approved, video_path)
                        sheet_success, sheet_msg = quick_update_from_publish_result(
                            video_title=formatted_title,
                            publish_results=results,
                            duration="",
                            source_lang=self.src_lang_var.get() or "English",
                            target_lang=self.tgt_lang_var.get() or "Gujarati",
                            content_format="",  # keep blank for videos in sheet
                        )
                        log("PUBLISH", f"✅ Google Sheet update: {sheet_msg}")
                    
                    except ImportError:
                        log("PUBLISH", "⚠️ Google Sheet logger not available")
                
                self._queue_ui(lambda: self.run_btn.config(state="normal"))
                self._queue_ui(self.progress.stop)
                self._queue_ui(lambda: self.status_var.set(msg))
                log("PUBLISH", f"✅ Publishing completed: {msg}")
                _safe_done(success=(ok > 0), msg=msg, pub_results=results)
                
            except Exception as e:
                log("PUBLISH", f"❌ Publishing error: {e}")
                self._queue_ui(lambda: self.run_btn.config(state="normal"))
                self._queue_ui(self.progress.stop)
                self._queue_ui(lambda: self.status_var.set(f"Publishing failed: {e}"))
                _safe_done(success=False, msg=f"Publishing failed: {e}", pub_results={"error": str(e)})
        
        threading.Thread(target=_publish, daemon=True).start()

    def _done_cb(self, success, msg, pub_results=None):
        self.progress.stop()
        self.status_var.set(msg)
        self.run_btn.config(state="normal")
        if pub_results:
            for k, v in pub_results.items():
                print(f'OK   {k}: id={v.get("_id","?") if isinstance(v,dict) else "ok"}')
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
        # Debug logging
        print(f"[STATUS] Progress update: {platform} -> {status} ({done}/{total})")
        
        if status == "posting":
            self.status_var.set(f"Posting to {platform} ...")
        elif status == "ok":
            self.status_var.set(f"✓ {platform} published")
        elif status == "error":
            self.status_var.set(f"✗ {platform} failed")
        elif status == "timeout":
            self.status_var.set(f"⏱ {platform} timed out")
        elif status == "skipped":
            self.status_var.set(f"⊘ {platform} skipped")
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


if __name__ == "__main__":
    App().mainloop()
