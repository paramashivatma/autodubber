import tkinter as tk
from tkinter import ttk
from dubber.utils import PLATFORMS, PLATFORM_LIMITS

class ReviewDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        captions,
        upload_manager=None,
        platforms=None,
        on_approve=None,
        on_cancel=None,
    ):
        """Review + publish-progress dialog.

        Two modes:
          * Synchronous (on_approve=None, legacy): __init__ blocks via
            wait_window(); _approve() destroys the dialog; caller reads
            self.result. Kept for the flyer publish path.
          * Async (on_approve=callable): __init__ returns immediately; on
            _approve(), the dialog stays alive, invokes
            on_approve(captions_dict), and becomes the live publish-progress
            surface. The caller must call update_progress() and
            publishing_complete() during/after the publish thread. The
            dialog destroys itself when the user clicks Close.
        """
        super().__init__(parent)
        self.title("Review Captions Before Publishing")
        self.grab_set()
        self.resizable(True, True)
        self.result    = None
        self._captions = captions
        self._platforms = list(platforms or PLATFORMS)
        self._widgets  = {}
        self._publishing = False
        self._upload_manager = upload_manager
        self._on_approve = on_approve
        self._on_cancel = on_cancel
        self._build(captions)
        self.geometry("700x600")  # Reasonable size

        # Start parallel uploads if upload manager provided
        if self._upload_manager:
            self._upload_manager.start_uploads(self._upload_progress_callback)

        # Legacy synchronous mode: block until the dialog is destroyed.
        # Async mode returns immediately so the caller can spawn a publish
        # thread while the dialog stays visible.
        if self._on_approve is None:
            self.wait_window()

    def _build(self, captions):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=False, padx=12, pady=6)  # Reduced padding

        for p in self._platforms:
            data  = captions.get(p, {})
            frame = tk.Frame(nb, padx=6, pady=4)
            nb.add(frame, text=f"  {p.capitalize()}  ")

            if p == "youtube":
                tk.Label(frame, text="Title:", font=("Helvetica",9,"bold")).pack(anchor="w")
                title_box = tk.Text(frame, height=2, wrap="word", font=("Helvetica",9))
                title_box.insert("1.0", data.get("title",""))
                title_box.pack(fill="x", pady=(0,4))
                self._widgets["youtube_title"] = title_box

            lim = PLATFORM_LIMITS.get(p, 2000)
            tk.Label(frame, text=f"Caption (limit: {lim} chars):",
                     font=("Helvetica",9,"bold")).pack(anchor="w")

            sf = tk.Frame(frame); sf.pack(fill="both", expand=True)
            sb = tk.Scrollbar(sf); sb.pack(side="right", fill="y")
            cap_box = tk.Text(sf, wrap="word", font=("Helvetica",9), yscrollcommand=sb.set, height=6)  # Reduced height
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

        # Progress/Results area (shown immediately for upload progress)
        self._progress_frame = tk.Frame(self)
        self._progress_frame.pack(fill="x", padx=12, pady=(0,6))
        
        tk.Label(self._progress_frame, text="Upload Progress:", 
                 font=("Helvetica",10,"bold"), fg="#2196f3").pack(anchor="w")
        
        self._progress_text = tk.Text(self._progress_frame, height=3, wrap="word",  # Compact height
                                      font=("Helvetica",9), bg="#f5f5f5")
        self._progress_text.pack(fill="x", pady=(4,0))
        
        # Initially show upload progress
        self._progress_text.insert(tk.END, "🔄 Starting parallel uploads...\n")
        self._progress_text.see(tk.END)
        
        # Status label
        self._status_lbl = tk.Label(self, text="Edit captions above, then click 'Approve & Publish'", 
                                    fg="#555", font=("Helvetica",9))
        self._status_lbl.pack(padx=12, pady=(0,2))

        btn = tk.Frame(self); btn.pack(fill="x", padx=12, pady=6)
        self._approve_btn = tk.Button(btn, text="Approve & Publish", width=18,
                  bg="#2e7d32", fg="white", font=("Helvetica",9,"bold"),
                  command=self._approve)
        self._approve_btn.pack(side="left", padx=4)
        
        self._cancel_btn = tk.Button(btn, text="Cancel", width=10,
                  bg="#c62828", fg="white", font=("Helvetica",9,"bold"),
                  command=self._cancel)
        self._cancel_btn.pack(side="left", padx=4)
        
        self._close_btn = tk.Button(btn, text="Close", width=10,
                  bg="#666", fg="white", font=("Helvetica",9,"bold"),
                  command=self.destroy)
        self._close_btn.pack(side="left", padx=4)
        self._close_btn.pack_forget()  # Hide initially

    def _upload_progress_callback(self, message, file_type=None, status=None):
        """Callback for upload progress updates"""
        if status == "uploading":
            self._progress_text.insert(tk.END, f"🔄 {message}\n")
        elif status == "completed":
            self._progress_text.insert(tk.END, f"✅ {message}\n")
        elif status == "error":
            self._progress_text.insert(tk.END, f"❌ {message}\n")
        else:
            self._progress_text.insert(tk.END, f"{message}\n")
        
        self._progress_text.see(tk.END)
        self.update_idletasks()

    def get_upload_results(self):
        """Get upload results from upload manager"""
        if self._upload_manager:
            return self._upload_manager.get_upload_results()
        return {}

    def _approve(self):
        result = {}
        for p in self._platforms:
            data = dict(self._captions.get(p,{}))
            if p in self._widgets:
                data["caption"] = self._widgets[p].get("1.0",tk.END).strip()
            if p == "youtube" and "youtube_title" in self._widgets:
                data["title"] = self._widgets["youtube_title"].get("1.0",tk.END).strip()
            result[p] = data
        self.result = result

        # Switch to publishing mode
        self._publishing = True
        self._status_lbl.config(text="Publishing in progress...", fg="#2e7d32")
        self._approve_btn.config(state="disabled")
        self._cancel_btn.config(text="Cancel Publish", command=self._cancel)

        # Update progress label to show publishing progress
        for widget in self._progress_frame.winfo_children():
            if isinstance(widget, tk.Label) and "Upload Progress:" in widget.cget("text"):
                widget.config(text="Publishing Progress:", fg="#2e7d32")
                break

        self._progress_text.insert(tk.END, "\n✅ Captions approved. Starting publishing...\n")
        self._progress_text.see(tk.END)

        if self._on_approve is not None:
            # Async mode: dialog stays alive as the live publish-progress
            # surface. Hand approved captions to caller and keep the window.
            try:
                self._on_approve(result)
            except Exception as e:
                # If the caller's hook blows up, degrade gracefully: surface
                # the error in the dialog instead of dying silently.
                try:
                    self._progress_text.insert(
                        tk.END, f"\n❌ Publish trigger failed: {e}\n"
                    )
                    self._progress_text.see(tk.END)
                    self._status_lbl.config(
                        text=f"❌ Publish trigger failed: {e}", fg="#c62828"
                    )
                except Exception:
                    pass
            return

        # Legacy synchronous mode: close dialog so caller can read dlg.result
        # and continue with its publish flow.
        self.destroy()

    def update_progress(self, message, platform=None, status=None):
        """Update the progress display with publishing status"""
        try:
            # Check if widget still exists before trying to use it
            if not hasattr(self, '_progress_text') or not self._progress_text.winfo_exists():
                return
                
            if not self._publishing:
                return
                
            if platform and status:
                if status == "started":
                    self._progress_text.insert(tk.END, f"🔄 Publishing to {platform}...\n")
                elif status == "success":
                    self._progress_text.insert(tk.END, f"✅ Published to {platform}\n")
                elif status == "error":
                    self._progress_text.insert(tk.END, f"❌ Failed on {platform}: {message}\n")
                else:
                    self._progress_text.insert(tk.END, f"{message}\n")
            else:
                self._progress_text.insert(tk.END, f"{message}\n")
                
            self._progress_text.see(tk.END)
            self.update_idletasks()
            
        except tk.TclError as e:
            # Widget was destroyed, ignore the error
            print(f"[PROGRESS] Widget destroyed: {e}")
        except Exception as e:
            # Other errors, print but don't crash
            print(f"[PROGRESS] Error: {e}")

    def publishing_complete(self, success=True, message=""):
        """Call when publishing is complete"""
        try:
            self._publishing = False
            
            # Check if widgets still exist
            if hasattr(self, '_status_lbl') and self._status_lbl.winfo_exists():
                if success:
                    self._status_lbl.config(text=f"✅ {message}", fg="#2e7d32")
                else:
                    self._status_lbl.config(text=f"❌ {message}", fg="#c62828")
            
            if hasattr(self, '_progress_text') and self._progress_text.winfo_exists():
                if success:
                    self._progress_text.insert(tk.END, f"\n🎉 {message}\n")
                else:
                    self._progress_text.insert(tk.END, f"\n❌ {message}\n")
                self._progress_text.see(tk.END)
            
            # Update buttons
            if hasattr(self, '_approve_btn') and self._approve_btn.winfo_exists():
                self._approve_btn.pack_forget()
            if hasattr(self, '_cancel_btn') and self._cancel_btn.winfo_exists():
                self._cancel_btn.pack_forget()
            if hasattr(self, '_close_btn') and self._close_btn.winfo_exists():
                self._close_btn.pack(side="left", padx=6)
                
        except tk.TclError as e:
            print(f"[COMPLETE] Widget destroyed: {e}")
        except Exception as e:
            print(f"[COMPLETE] Error: {e}")
        
    def _cancel(self):
        if self._publishing:
            # Cancel publishing (UI-only; the publish thread still finishes
            # its current in-flight request).
            self._publishing = False
            self.result = None  # Signal cancellation
            self._status_lbl.config(text="Publishing cancelled.", fg="#c62828")
            self._progress_text.insert(tk.END, "\n❌ Publishing cancelled by user.\n")
            self._progress_text.see(tk.END)

            self._approve_btn.pack_forget()
            self._cancel_btn.pack_forget()
            self._close_btn.pack(side="left", padx=6)
        else:
            # Normal cancel (before approval)
            self.result = None
            if self._on_cancel is not None:
                try:
                    self._on_cancel()
                except Exception:
                    pass
            self.destroy()

    def is_publishing(self):
        """Check if currently in publishing mode"""
        return self._publishing
