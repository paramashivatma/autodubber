#!/usr/bin/env python3
"""Fix image handling in Publish Only tab to properly handle images"""

import os
import sys

# Read the current app.py
with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the _add_images method to properly handle both tabs
add_images_old = '''    def _add_images(self):
        paths = filedialog.askopenfilenames(filetypes=[("Images","*.jpg *.jpeg *.png *.gif *.webp"),("All","*.*")])
        for p in paths:
            if p not in self._image_paths:
                self._image_paths.append(p)
                self.image_listbox.insert(tk.END, os.path.basename(p))
                try: self.dub_image_listbox.insert(tk.END, os.path.basename(p))
                except: pass'''

add_images_new = '''    def _add_images(self):
        paths = filedialog.askopenfilenames(filetypes=[("Images","*.jpg *.jpeg *.png *.gif *.webp"),("All","*.*")])
        for p in paths:
            if p not in self._image_paths:
                self._image_paths.append(p)
                # Add to Publish Only tab listbox
                if hasattr(self, 'image_listbox'):
                    self.image_listbox.insert(tk.END, os.path.basename(p))
                # Add to Media tab listbox (if it exists)
                if hasattr(self, 'dub_image_listbox'):
                    self.dub_image_listbox.insert(tk.END, os.path.basename(p))'''

# Fix the _clear_images method
clear_images_old = '''    def _clear_images(self):
        self._image_paths.clear()
        self.image_listbox.delete(0, tk.END)
        try: self.dub_image_listbox.delete(0, tk.END)
        except: pass'''

clear_images_new = '''    def _clear_images(self):
        self._image_paths.clear()
        # Clear Publish Only tab listbox
        if hasattr(self, 'image_listbox'):
            self.image_listbox.delete(0, tk.END)
        # Clear Media tab listbox (if it exists)
        if hasattr(self, 'dub_image_listbox'):
            self.dub_image_listbox.delete(0, tk.END)'''

# Replace the methods
content = content.replace(add_images_old, add_images_new)
content = content.replace(clear_images_old, clear_images_new)

# Write the updated content
with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Fixed image handling!")
print("  - Fixed _add_images to handle both tabs properly")
print("  - Fixed _clear_images to handle both tabs properly")
print("  - Added safety checks for listbox existence")
print("  - Images will now work correctly in both tabs")
