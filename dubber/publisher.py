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

    # track per-platform results for the log
    self._pub_results_live = {}

    def _progress(done, total, platform, status):
        """
        Called from background thread — must use self.after() for any UI update.
        done   = completed count
        total  = total platforms
        status = 'posting' | 'ok' | 'timeout' | 'error' | 'skipped'
        """
        pct = int((done / total) * 100) if total else 0

        STATUS_EMOJI = {
            "posting": "⏳",
            "ok":      "✅",
            "timeout": "⚠️",
            "error":   "❌",
            "skipped": "⏭️",
        }
        emoji = STATUS_EMOJI.get(status, "")

        # update status bar
        if status == "posting":
            msg = f"Publishing... {pct}%  —  {emoji} {platform} posting..."
        else:
            msg = f"Publishing... {pct}%  —  {emoji} {platform} {status}"

        self.after(0, lambda m=msg: self.status_var.set(m))

        # write to the pub log box in the UI
        if status != "posting":   # only log final state, not the "in progress" notice
            log_line = f"{emoji} {platform.upper():<12} {status.upper()}"
            self.after(0, lambda l=log_line: self._pub_log_write(l))

    def _publish():
        try:
            teaser_caps = {p: {"caption": approved.get(p, {}).get("caption", "")[:180]}
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
                progress_cb     = _progress,
            )
            ok  = sum(1 for v in results.values()
                      if isinstance(v, dict) and "error" not in v)
            tmo = sum(1 for v in results.values()
                      if isinstance(v, dict) and v.get("error") == "timeout-unconfirmed")
            skp = sum(1 for v in results.values()
                      if isinstance(v, dict) and v.get("skipped"))

            if ok == len(selected_platforms):
                msg = f"All {ok} platform(s) published successfully."
            elif tmo:
                msg = f"{ok} OK, {tmo} timed out (likely posted — verify on Zernio), {len(selected_platforms)-ok-tmo} failed."
            else:
                msg = f"{ok}/{len(selected_platforms)} published. Check log for failures."

            done_cb(success=bool(ok or tmo), msg=msg, pub_results=results)
        except Exception as e:
            import traceback; traceback.print_exc()
            done_cb(success=False, msg=str(e), pub_results={})

    threading.Thread(target=_publish, daemon=True).start()