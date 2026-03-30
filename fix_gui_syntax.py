#!/usr/bin/env python3
"""Fix GUI syntax error in the Media tab"""

import os
import sys

# Read the current app.py
with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the syntax error - remove duplicate padx argument
content = content.replace(
    'tk.Checkbutton(self.t_media, text="Extract text from flyer/image",\n                       variable=self.extract_text_var).grid(row=6,column=0,columnspan=3,sticky="w",padx=10,**pad)',
    'tk.Checkbutton(self.t_media, text="Extract text from flyer/image",\n                       variable=self.extract_text_var).grid(row=6,column=0,columnspan=3,sticky="w",padx=10)'
)

content = content.replace(
    'tk.Checkbutton(self.t_media, text="Generate Gujarati captions",\n                       variable=self.generate_captions_var).grid(row=7,column=0,columnspan=3,sticky="w",padx=10,**pad)',
    'tk.Checkbutton(self.t_media, text="Generate Gujarati captions",\n                       variable=self.generate_captions_var).grid(row=7,column=0,columnspan=3,sticky="w",padx=10)'
)

content = content.replace(
    'tk.Checkbutton(self.t_media, text="Create teaser content",\n                       variable=self.generate_teaser_var).grid(row=8,column=0,columnspan=3,sticky="w",padx=10,**pad)',
    'tk.Checkbutton(self.t_media, text="Create teaser content",\n                       variable=self.generate_teaser_var).grid(row=8,column=0,columnspan=3,sticky="w",padx=10)'
)

# Write the updated content
with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Fixed GUI syntax error!")
print("  - Removed duplicate padx arguments")
print("  - Fixed checkbutton grid configurations")
