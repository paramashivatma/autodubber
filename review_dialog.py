import tkinter as tk
from tkinter import ttk
from dubber.utils import PLATFORMS, PLATFORM_LIMITS

class ReviewDialog(tk.Toplevel):
    def __init__(self, parent, captions):
        super().__init__(parent)
        self.title("Review Captions Before Publishing")
        self.grab_set()
        self.resizable(True, True)
        self.result    = None
        self._captions = captions
        self._widgets  = {}
        self._build(captions)
        self.geometry("820x660")
        self.wait_window()

    def _build(self, captions):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        for p in PLATFORMS:
            data  = captions.get(p, {})
            frame = tk.Frame(nb, padx=8, pady=6)
            nb.add(frame, text=f"  {p.capitalize()}  ")

            if p == "youtube":
                tk.Label(frame, text="Title:", font=("Helvetica",9,"bold")).pack(anchor="w")
                title_box = tk.Text(frame, height=2, wrap="word", font=("Helvetica",9))
                title_box.insert("1.0", data.get("title",""))
                title_box.pack(fill="x", pady=(0,6))
                self._widgets["youtube_title"] = title_box

            lim = PLATFORM_LIMITS.get(p, 2000)
            tk.Label(frame, text=f"Caption (limit: {lim} chars):",
                     font=("Helvetica",9,"bold")).pack(anchor="w")

            sf = tk.Frame(frame); sf.pack(fill="both", expand=True)
            sb = tk.Scrollbar(sf); sb.pack(side="right", fill="y")
            cap_box = tk.Text(sf, wrap="word", font=("Helvetica",9), yscrollcommand=sb.set)
            cap_box.insert("1.0", data.get("caption",""))
            cap_box.pack(side="left", fill="both", expand=True)
            sb.config(command=cap_box.yview)
            self._widgets[p] = cap_box

            count_lbl = tk.Label(frame, text="", fg="#888", font=("Helvetica",8))
            count_lbl.pack(anchor="e")
            def _upd(e=None, b=cap_box, l=count_lbl, lim=lim):
                n = len(b.get("1.0",tk.END).strip())
                l.config(text=f"{n}/{lim}", fg="#c00" if n>lim else "#888")
            cap_box.bind("<KeyRelease>", _upd); _upd()

        btn = tk.Frame(self); btn.pack(fill="x", padx=8, pady=8)
        tk.Button(btn, text="Approve & Publish", width=20,
                  bg="#2e7d32", fg="white", font=("Helvetica",10,"bold"),
                  command=self._approve).pack(side="left", padx=6)
        tk.Button(btn, text="Cancel", width=12,
                  bg="#c62828", fg="white", font=("Helvetica",10,"bold"),
                  command=self.destroy).pack(side="left", padx=6)
        tk.Label(btn, text="Edit any caption above, then approve.",
                 fg="#555", font=("Helvetica",8)).pack(side="left", padx=8)

    def _approve(self):
        result = {}
        for p in PLATFORMS:
            data = dict(self._captions.get(p,{}))
            if p in self._widgets:
                data["caption"] = self._widgets[p].get("1.0",tk.END).strip()
            if p == "youtube" and "youtube_title" in self._widgets:
                data["title"] = self._widgets["youtube_title"].get("1.0",tk.END).strip()
            result[p] = data
        self.result = result
        self.destroy()