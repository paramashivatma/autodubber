import os, shutil, threading, tkinter as tk
from tkinter import filedialog, ttk, messagebox

from dubber import (
    transcribe_audio, merge_short_segments, translate_segments,
    generate_tts_audio, build_dubbed_video,
    extract_vision, generate_all_captions,
    generate_teaser, generate_teasers, publish_to_platforms, log,
)
from dubber.downloader    import is_url, download_video
from dubber.bgm_separator import separate_background
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
PLATFORMS = ["instagram","threads","facebook","bluesky","youtube","twitter","tiktok"]

def _load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=",1); env[k.strip()] = v.strip()
    return env

def _save_env(data):
    e = _load_env(); e.update(data)
    with open(ENV_FILE,"w") as f:
        for k,v in e.items(): f.write(f"{k}={v}\n")


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
        self.title("Video Dubber v24  |  Dub / Publish")
        self.resizable(False, False)
        self._env         = _load_env()
        self._image_paths = []
        self._build_ui()

    def _build_ui(self):
        pad = {"padx":10,"pady":4}

        top = tk.Frame(self, bg="#1a1a2e", pady=6)
        top.pack(fill="x")
        tk.Label(top, text="Mode:", fg="white", bg="#1a1a2e",
                 font=("Helvetica",10,"bold")).pack(side="left", padx=12)
        self.mode_var = tk.StringVar(value="dub")
        tk.Radiobutton(top, text="Full Dub Pipeline", variable=self.mode_var,
                       value="dub", bg="#1a1a2e", fg="white",
                       selectcolor="#333", activebackground="#1a1a2e",
                       font=("Helvetica",10,"bold"),
                       command=self._on_mode_change).pack(side="left", padx=8)
        tk.Radiobutton(top, text="Publish Only (Images / Teaser)", variable=self.mode_var,
                       value="publish", bg="#1a1a2e", fg="#00e5ff",
                       selectcolor="#333", activebackground="#1a1a2e",
                       font=("Helvetica",10,"bold"),
                       command=self._on_mode_change).pack(side="left", padx=8)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=6)

        self.t_dub = tk.Frame(self.nb, padx=14, pady=10)
        self.nb.add(self.t_dub, text="  Dub  ")

        tk.Label(self.t_dub, text="Video / URL:").grid(row=0,column=0,sticky="w",**pad)
        self.video_var = tk.StringVar()
        tk.Entry(self.t_dub, textvariable=self.video_var, width=42).grid(row=0,column=1,**pad)
        tk.Button(self.t_dub, text="Browse", command=self._browse_video).grid(row=0,column=2,**pad)

        tk.Label(self.t_dub, text="Voice:").grid(row=1,column=0,sticky="w",**pad)
        self.voice_var = tk.StringVar(value=list(VOICES.keys())[0])
        ttk.Combobox(self.t_dub, textvariable=self.voice_var, values=list(VOICES.keys()),
                     width=32, state="readonly").grid(row=1,column=1,columnspan=2,**pad)

        tk.Label(self.t_dub, text="Whisper model:").grid(row=2,column=0,sticky="w",**pad)
        self.model_var = tk.StringVar(value="large")
        ttk.Combobox(self.t_dub, textvariable=self.model_var, values=WHISPER_MODELS,
                     width=12, state="readonly").grid(row=2,column=1,sticky="w",**pad)

        tk.Label(self.t_dub, text="Source lang:").grid(row=3,column=0,sticky="w",**pad)
        self.src_lang_var = tk.StringVar(value="English")
        ttk.Combobox(self.t_dub, textvariable=self.src_lang_var,
                     values=list(LANGUAGES.keys()), width=14,
                     state="readonly").grid(row=3,column=1,sticky="w",**pad)

        tk.Label(self.t_dub, text="Target lang:").grid(row=4,column=0,sticky="w",**pad)
        self.tgt_lang_var = tk.StringVar(value="Gujarati")
        ttk.Combobox(self.t_dub, textvariable=self.tgt_lang_var,
                     values=list(LANGUAGES.keys()), width=14,
                     state="readonly").grid(row=4,column=1,sticky="w",**pad)

        ttk.Separator(self.t_dub,orient="horizontal").grid(row=5,column=0,columnspan=3,sticky="ew",pady=6)
        self.bgm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.t_dub, text="Preserve background music (demucs)",
                       variable=self.bgm_var, command=self._toggle_bgm
                       ).grid(row=6,column=0,columnspan=2,sticky="w",**pad)
        tk.Label(self.t_dub, text="Music volume:").grid(row=7,column=0,sticky="w",**pad)
        self.bgm_vol_var = tk.DoubleVar(value=0.35)
        self.bgm_scale = tk.Scale(self.t_dub, variable=self.bgm_vol_var,
                                  from_=0.0, to=1.0, resolution=0.05,
                                  orient="horizontal", length=150)
        self.bgm_scale.grid(row=7,column=1,sticky="w",**pad)

        self.t_pub = tk.Frame(self.nb, padx=14, pady=10)
        self.nb.add(self.t_pub, text="  Publish Only  ")

        tk.Label(self.t_pub, text="Topic / Hook hint for AI captions:",
                 font=("Helvetica",9,"bold")).grid(row=0,column=0,columnspan=3,sticky="w",**pad)
        self.topic_var = tk.StringVar()
        tk.Entry(self.t_pub, textvariable=self.topic_var, width=52).grid(row=1,column=0,columnspan=3,**pad)
        tk.Label(self.t_pub, text="Leave blank to write captions manually in the review screen.",
                 fg="#888", font=("Helvetica",8)).grid(row=2,column=0,columnspan=3,sticky="w",padx=10)

        ttk.Separator(self.t_pub,orient="horizontal").grid(row=3,column=0,columnspan=3,sticky="ew",pady=8)
        tk.Label(self.t_pub, text="Images to post:", font=("Helvetica",9,"bold")).grid(row=4,column=0,sticky="w",**pad)
        tk.Button(self.t_pub, text="+ Add Images", command=self._add_images).grid(row=4,column=1,sticky="w",**pad)
        tk.Button(self.t_pub, text="Clear All", command=self._clear_images).grid(row=4,column=2,sticky="w")
        self.image_listbox = tk.Listbox(self.t_pub, width=52, height=5, font=("Helvetica",8))
        self.image_listbox.grid(row=5,column=0,columnspan=3,padx=10,pady=4)

        ttk.Separator(self.t_pub,orient="horizontal").grid(row=6,column=0,columnspan=3,sticky="ew",pady=8)
        tk.Label(self.t_pub, text="Teaser clip (optional):", font=("Helvetica",9,"bold")).grid(row=7,column=0,sticky="w",**pad)
        self.pub_teaser_var = tk.StringVar()
        tk.Entry(self.t_pub, textvariable=self.pub_teaser_var, width=34).grid(row=7,column=1,**pad)
        tk.Button(self.t_pub, text="Browse", command=self._browse_pub_teaser).grid(row=7,column=2,**pad)
        tk.Button(self.t_pub, text="Clear", command=lambda: self.pub_teaser_var.set("")).grid(row=8,column=2,pady=0)

        self.t_media = tk.Frame(self.nb, padx=14, pady=10)
        self.nb.add(self.t_media, text="  Media  ")

        tk.Label(self.t_media, text="Teaser Clip", font=("Helvetica",10,"bold")).grid(row=0,column=0,columnspan=3,sticky="w",**pad)
        self.auto_teaser_var = tk.BooleanVar(value=True)
        tk.Radiobutton(self.t_media, text="Auto-generate from dubbed video (6-10s hook)",
                       variable=self.auto_teaser_var, value=True,
                       command=self._toggle_teaser).grid(row=1,column=0,columnspan=3,sticky="w",**pad)
        tk.Radiobutton(self.t_media, text="Manual teaser file:",
                       variable=self.auto_teaser_var, value=False,
                       command=self._toggle_teaser).grid(row=2,column=0,sticky="w",**pad)
        self.manual_teaser_var = tk.StringVar()
        self.manual_teaser_entry = tk.Entry(self.t_media, textvariable=self.manual_teaser_var,
                                            width=34, state="disabled")
        self.manual_teaser_entry.grid(row=2,column=1,**pad)
        self.manual_teaser_btn = tk.Button(self.t_media, text="Browse", state="disabled",
                                            command=self._browse_teaser)
        self.manual_teaser_btn.grid(row=2,column=2,**pad)
        tk.Button(self.t_media, text="No teaser",
                  command=lambda:[self.auto_teaser_var.set(False),
                                  self.manual_teaser_var.set(""),
                                  self._toggle_teaser()]
                  ).grid(row=3,column=0,sticky="w",padx=10,pady=2)

        ttk.Separator(self.t_media,orient="horizontal").grid(row=4,column=0,columnspan=3,sticky="ew",pady=8)
        tk.Label(self.t_media, text="Extra Images (attach alongside video)",
                 font=("Helvetica",10,"bold")).grid(row=5,column=0,columnspan=3,sticky="w",**pad)
        bf = tk.Frame(self.t_media); bf.grid(row=6,column=0,columnspan=3,sticky="w",padx=10)
        tk.Button(bf,text="+ Add Images",command=self._add_images).pack(side="left",padx=4)
        tk.Button(bf,text="Clear All",command=self._clear_images).pack(side="left",padx=4)
        self.dub_image_listbox = tk.Listbox(self.t_media,width=52,height=4,font=("Helvetica",8))
        self.dub_image_listbox.grid(row=7,column=0,columnspan=3,padx=10,pady=4)

        self.t_api = tk.Frame(self.nb, padx=14, pady=10)
        self.nb.add(self.t_api, text="  AI & Publish  ")

        tk.Label(self.t_api, text="Gemini Vision Key:").grid(row=0,column=0,sticky="w",**pad)
        self.gemini_vision_key_var = tk.StringVar(value=self._env.get("GEMINI_VISION_KEY",""))
        tk.Entry(self.t_api, textvariable=self.gemini_vision_key_var, width=42, show="*").grid(row=0,column=1,columnspan=2,**pad)

        tk.Label(self.t_api, text="Mistral API Key:").grid(row=1,column=0,sticky="w",**pad)
        self.mistral_key_var = tk.StringVar(value=self._env.get("MISTRAL_API_KEY",""))
        tk.Entry(self.t_api, textvariable=self.mistral_key_var, width=42, show="*").grid(row=1,column=1,columnspan=2,**pad)

        tk.Label(self.t_api, text="Zernio API Key:").grid(row=2,column=0,sticky="w",**pad)
        self.zernio_key_var = tk.StringVar(value=self._env.get("ZERNIO_API_KEY",""))
        tk.Entry(self.t_api, textvariable=self.zernio_key_var, width=42, show="*").grid(row=2,column=1,columnspan=2,**pad)
        tk.Button(self.t_api, text="Save Keys", command=self._save_keys).grid(row=2,column=3,**pad)

        tk.Label(self.t_api, text="Platforms:").grid(row=3,column=0,sticky="nw",**pad)
        self._plat_vars = {}
        pf = tk.Frame(self.t_api); pf.grid(row=3,column=1,columnspan=3,sticky="w")
        for i,p in enumerate(PLATFORMS):
            v = tk.BooleanVar(value=True); self._plat_vars[p] = v
            tk.Checkbutton(pf,text=p.capitalize(),variable=v).grid(row=i//4,column=i%4,sticky="w",padx=6)

        ttk.Separator(self.t_api,orient="horizontal").grid(row=4,column=0,columnspan=4,sticky="ew",pady=6)
        self.publish_now_var = tk.BooleanVar(value=True)
        tk.Radiobutton(self.t_api, text="Publish immediately",
                       variable=self.publish_now_var, value=True,
                       command=self._toggle_schedule).grid(row=5,column=0,columnspan=2,sticky="w",**pad)
        tk.Radiobutton(self.t_api, text="Schedule for:",
                       variable=self.publish_now_var, value=False,
                       command=self._toggle_schedule).grid(row=6,column=0,sticky="w",**pad)
        self.schedule_var   = tk.StringVar(value="2026-03-26T10:00:00Z")
        self.schedule_entry = tk.Entry(self.t_api, textvariable=self.schedule_var,
                                       width=24, state="disabled")
        self.schedule_entry.grid(row=6,column=1,sticky="w",**pad)
        tk.Label(self.t_api, text="ISO8601 UTC", fg="#888", font=("Helvetica",8)).grid(row=6,column=2,sticky="w")

        ttk.Separator(self.t_api,orient="horizontal").grid(row=7,column=0,columnspan=4,sticky="ew",pady=6)
        tk.Label(self.t_api, text="Publish log:", font=("Helvetica",9,"bold")).grid(row=8,column=0,sticky="w",**pad)
        self.pub_log = tk.Text(self.t_api, width=54, height=5, wrap="word",
                               font=("Courier",8), state="disabled")
        self.pub_log.grid(row=9,column=0,columnspan=4,**pad)

        bot = tk.Frame(self, padx=14, pady=6); bot.pack(fill="x")
        self.run_btn = tk.Button(bot, text="Run Pipeline", width=20,
                                 bg="#2e7d32", fg="white",
                                 font=("Helvetica",11,"bold"), command=self._run)
        self.run_btn.pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(bot, textvariable=self.status_var, fg="#555", wraplength=340).pack(side="left", padx=10)
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=480)
        self.progress.pack(fill="x", padx=14, pady=(0,8))

        self._on_mode_change()

    def _on_mode_change(self):
        mode = self.mode_var.get()
        dub_state = "normal" if mode == "dub" else "disabled"
        self.nb.tab(0, state=dub_state)
        self.nb.tab(2, state=dub_state)
        pub_state = "normal" if mode == "publish" else "disabled"
        self.nb.tab(1, state=pub_state)
        if mode == "dub":
            self.nb.select(0)
            self.run_btn.config(text="Run Full Pipeline")
        else:
            self.nb.select(1)
            self.run_btn.config(text="Publish Now")

    def _toggle_bgm(self):
        self.bgm_scale.config(state="normal" if self.bgm_var.get() else "disabled")

    def _toggle_teaser(self):
        manual = not self.auto_teaser_var.get()
        st = "normal" if manual else "disabled"
        self.manual_teaser_entry.config(state=st)
        self.manual_teaser_btn.config(state=st)

    def _toggle_schedule(self):
        self.schedule_entry.config(state="normal" if not self.publish_now_var.get() else "disabled")

    def _browse_video(self):
        p = filedialog.askopenfilename(filetypes=[("Video","*.mp4 *.mov *.mkv *.avi *.webm"),("All","*.*")])
        if p: self.video_var.set(p)

    def _browse_teaser(self):
        p = filedialog.askopenfilename(filetypes=[("Video","*.mp4 *.mov *.mkv *.avi *.webm"),("All","*.*")])
        if p: self.manual_teaser_var.set(p)

    def _browse_pub_teaser(self):
        p = filedialog.askopenfilename(filetypes=[("Video","*.mp4 *.mov *.mkv *.avi *.webm"),("All","*.*")])
        if p: self.pub_teaser_var.set(p)

    def _add_images(self):
        paths = filedialog.askopenfilenames(filetypes=[("Images","*.jpg *.jpeg *.png *.gif *.webp"),("All","*.*")])
        for p in paths:
            if p not in self._image_paths:
                self._image_paths.append(p)
                self.image_listbox.insert(tk.END, os.path.basename(p))
                try: self.dub_image_listbox.insert(tk.END, os.path.basename(p))
                except: pass

    def _clear_images(self):
        self._image_paths.clear()
        self.image_listbox.delete(0, tk.END)
        try: self.dub_image_listbox.delete(0, tk.END)
        except: pass

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

    def _pub_log_clear(self):
        self.pub_log.config(state="normal")
        self.pub_log.delete("1.0",tk.END)
        self.pub_log.config(state="disabled")

    def _pub_log_write(self, text):
        self.pub_log.config(state="normal")
        self.pub_log.insert(tk.END, text+"\n")
        self.pub_log.config(state="disabled")

    def _run(self):
        mode = self.mode_var.get()
        self._pub_log_clear()
        selected       = [p for p,v in self._plat_vars.items() if v.get()]
        sched          = self.schedule_var.get().strip() if not self.publish_now_var.get() else None
        gemini_vision  = self.gemini_vision_key_var.get().strip()
        mistral        = self.mistral_key_var.get().strip()
        zernio         = self.zernio_key_var.get().strip()
        to_save = {}
        if gemini_vision: to_save["GEMINI_VISION_KEY"] = gemini_vision
        if mistral:       to_save["MISTRAL_API_KEY"]   = mistral
        if zernio:        to_save["ZERNIO_API_KEY"]     = zernio
        if to_save:       _save_env(to_save)

        if mode == "dub":
            video = self.video_var.get().strip()
            if not video:
                messagebox.showwarning("No input","Paste a URL or browse for a video.")
                return
            self.run_btn.config(state="disabled")
            self.progress.start(12); self.status_var.set("Starting dub pipeline ...")
            manual_teaser = self.manual_teaser_var.get().strip() if not self.auto_teaser_var.get() else ""
            threading.Thread(target=run_dub_pipeline, args=(
                video, VOICES[self.voice_var.get()], self.model_var.get(),
                LANGUAGES[self.src_lang_var.get()], LANGUAGES[self.tgt_lang_var.get()],
                self.bgm_var.get(), self.bgm_vol_var.get(),
                gemini_vision, mistral, zernio, selected,
                self.publish_now_var.get(), sched,
                self.auto_teaser_var.get(), manual_teaser,
                list(self._image_paths),
                self.status_var.set, self._caption_ready_cb, self._done_cb,
            ), daemon=True).start()
        else:
            images = list(self._image_paths)
            teaser = self.pub_teaser_var.get().strip()
            if not images and not teaser:
                messagebox.showwarning("Nothing to publish",
                    "Add at least one image or a teaser clip to publish.")
                return
            self.run_btn.config(state="disabled")
            self.progress.start(12); self.status_var.set("Preparing publish ...")
            threading.Thread(target=run_publish_only, args=(
                images, teaser if teaser else None,
                self.topic_var.get().strip(),
                gemini_vision, mistral, zernio, selected,
                self.publish_now_var.get(), sched,
                self.status_var.set, self._caption_ready_cb, self._done_cb,
            ), daemon=True).start()

    def _caption_ready_cb(self, **kwargs):
        self.after(0, lambda: self._show_review(**kwargs))

    def _show_review(self, captions, teaser_path, video_path, zernio_key,
                     selected_platforms, publish_now, scheduled_for,
                     image_paths, done_cb, teaser_paths=None):
        self.progress.stop()
        self.status_var.set("Review captions — edit if needed, then approve.")
        dlg = ReviewDialog(self, captions)
        if dlg.result is None:
            self.run_btn.config(state="normal")
            self.status_var.set("Publishing cancelled."); return
        approved = dlg.result
        self.progress.start(12); self.status_var.set("Publishing ...")

        def _publish():
            try:
                teaser_caps = {p:{"caption":approved.get(p,{}).get("caption","")[:180]}
                               for p in selected_platforms}
                results = publish_to_platforms(
                    api_key         = zernio_key,
                    video_path      = video_path,
                    captions        = approved,
                    platforms       = selected_platforms,
                    scheduled_for   = scheduled_for if not publish_now else None,
                    publish_now     = publish_now,
                    teaser_path     = teaser_path,
                    teaser_captions = teaser_caps if teaser_path else None,
                    image_paths     = image_paths or [],
                    output_dir      = WORKSPACE,
                )
                ok  = sum(1 for v in results.values() if not (isinstance(v,dict) and "error" in v))
                msg = f"Published {ok} post(s)." if ok else "All posts failed — check log."
                done_cb(success=bool(ok), msg=msg, pub_results=results)
            except Exception as e:
                import traceback; traceback.print_exc()
                done_cb(success=False, msg=str(e), pub_results={})

        threading.Thread(target=_publish, daemon=True).start()

    def _done_cb(self, success, msg, pub_results=None):
        self.progress.stop()
        self.run_btn.config(state="normal")
        self.status_var.set(msg)
        if pub_results:
            for k,v in pub_results.items():
                if isinstance(v,dict) and "error" in v:
                    self._pub_log_write(f'FAIL {k}: {v["error"]}')
                else:
                    self._pub_log_write(f'OK   {k}: id={v.get("_id","?") if isinstance(v,dict) else "ok"}')
        (messagebox.showinfo if success else messagebox.showerror)("Result", msg)


if __name__ == "__main__":
    App().mainloop()
