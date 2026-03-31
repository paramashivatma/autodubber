#!/usr/bin/env python3
"""Add cleanup to main dub pipeline"""

import os

# Read the current app.py
with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the _done_cb method and add cleanup for dub pipeline
done_cb_old = '''    def _done_cb(self, success, msg, pub_results=None):
        self.progress.stop()
        self.run_btn.config(state="normal")
        self.status_var.set(msg)
        if pub_results:
            for k,v in pub_results.items():
                if isinstance(v,dict) and "error" in v:
                    self._pub_log_write(f'FAIL {k}: {v["error"]}')
                else:
                    self._pub_log_write(f'OK   {k}: id={v.get("_id","?") if isinstance(v,dict) else "ok"}')
        (messagebox.showinfo if success else messagebox.showerror)("Result", msg)'''

done_cb_new = '''    def _done_cb(self, success, msg, pub_results=None):
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
        
        # Clean up workspace after pipeline completion
        try:
            from dubber.workspace_cleaner import cleanup_temp_files
            cleanup_temp_files("workspace")
            self.status_var.set(f"{msg} (workspace cleaned)")
        except Exception as e:
            self.status_var.set(f"{msg} (cleanup failed: {str(e)})")'''

# Replace the method
content = content.replace(done_cb_old, done_cb_new)

# Write the updated content
with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Added cleanup to main dub pipeline!")
print("  - Cleans up temp files after pipeline completion")
print("  - Updates status message with cleanup result")
