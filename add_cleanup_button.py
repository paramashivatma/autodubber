#!/usr/bin/env python3
"""Add manual cleanup button to GUI"""

import os

# Read the current app.py
with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the bot frame section and add cleanup button
bot_frame_old = '''        bot = tk.Frame(self, padx=14, pady=6); bot.pack(fill="x")
        self.run_btn = tk.Button(bot, text="Run Pipeline", width=20,
                                 bg="#2e7d32", fg="white",
                                 font=("Helvetica",11,"bold"), command=self._run)
        self.run_btn.pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(bot, textvariable=self.status_var, fg="#555", wraplength=340).pack(side="left", padx=10)'''

bot_frame_new = '''        bot = tk.Frame(self, padx=14, pady=6); bot.pack(fill="x")
        self.run_btn = tk.Button(bot, text="Run Pipeline", width=20,
                                 bg="#2e7d32", fg="white",
                                 font=("Helvetica",11,"bold"), command=self._run)
        self.run_btn.pack(side="left", padx=6)
        self.cleanup_btn = tk.Button(bot, text="🧹 Clean", width=12,
                                     bg="#ff6b35", fg="white",
                                     font=("Helvetica",10,"bold"), command=self._manual_cleanup)
        self.cleanup_btn.pack(side="left", padx=2)
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(bot, textvariable=self.status_var, fg="#555", wraplength=340).pack(side="left", padx=10)'''

# Replace the bot frame
content = content.replace(bot_frame_old, bot_frame_new)

# Add the manual cleanup method
new_method = '''
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
'''

# Find a good place to insert the method (before the existing _save_keys method)
save_keys_pos = content.find("    def _save_keys(self):")
if save_keys_pos != -1:
    content = content[:save_keys_pos] + new_method + "\n" + content[save_keys_pos:]
else:
    # If not found, add at the end before the main check
    main_check_pos = content.find("if __name__ == \"__main__\":")
    if main_check_pos != -1:
        content = content[:main_check_pos] + new_method + "\n" + content[main_check_pos:]
    else:
        content += "\n" + new_method

# Write the updated content
with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Added manual cleanup button to GUI!")
print("  - Added '🧹 Clean' button next to Run Pipeline")
print("  - Added _manual_cleanup method")
print("  - Shows status updates and confirmation dialog")
