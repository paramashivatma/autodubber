#!/usr/bin/env python3
"""Update the flyer processing to use real OCR and content generation"""

import os
import sys

# Read the current app.py
with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find and replace the _process_flyer method
old_process_method = '''    def _process_flyer(self):
        """Process flyer to extract text and generate content"""
        if not self.flyer_path:
            messagebox.showerror("Error", "Please select a flyer/image file first")
            return
        
        if not os.path.exists(self.flyer_path):
            messagebox.showerror("Error", "File not found")
            return
        
        try:
            self.flyer_results.delete(1.0, tk.END)
            self.flyer_results.insert(tk.END, "Processing flyer...\\n\\n")
            
            # Extract text from image (placeholder for OCR functionality)
            if self.extract_text_var.get():
                self.flyer_results.insert(tk.END, "📝 Extracting text from image...\\n")
                # TODO: Implement OCR here
                extracted_text = "Text extraction functionality to be implemented"
                self.flyer_results.insert(tk.END, f"Extracted text: {extracted_text}\\n\\n")
            
            # Generate Gujarati captions
            if self.generate_captions_var.get():
                self.flyer_results.insert(tk.END, "🎨 Generating Gujarati captions...\\n")
                # TODO: Implement caption generation
                captions = "Gujarati caption generation to be implemented"
                self.flyer_results.insert(tk.END, f"Captions: {captions}\\n\\n")
            
            # Generate teaser content
            if self.generate_teaser_var.get():
                self.flyer_results.insert(tk.END, "🎬 Creating teaser content...\\n")
                # TODO: Implement teaser generation
                teaser = "Teaser content generation to be implemented"
                self.flyer_results.insert(tk.END, f"Teaser: {teaser}\\n\\n")
            
            self.flyer_results.insert(tk.END, "✅ Processing complete!\\n")
            self.flyer_results.insert(tk.END, "Note: OCR and content generation features need to be implemented.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process flyer: {str(e)}")
            self.flyer_results.insert(tk.END, f"❌ Error: {str(e)}\\n")'''

new_process_method = '''    def _process_flyer(self):
        """Process flyer to extract text and generate content"""
        if not self.flyer_path:
            messagebox.showerror("Error", "Please select a flyer/image file first")
            return
        
        if not os.path.exists(self.flyer_path):
            messagebox.showerror("Error", "File not found")
            return
        
        try:
            self.flyer_results.delete(1.0, tk.END)
            self.flyer_results.insert(tk.END, "🔄 Processing flyer...\\n\\n")
            
            # Get API keys
            gemini_key = self.gemini_vision_key_var.get().strip()
            
            extracted_text = ""
            captions = {}
            teaser = {}
            
            # Extract text from image
            if self.extract_text_var.get():
                self.flyer_results.insert(tk.END, "📝 Extracting text from image...\\n")
                try:
                    from dubber.image_processor import extract_text_from_image
                    extracted_text = extract_text_from_image(self.flyer_path, gemini_key)
                    self.flyer_results.insert(tk.END, f"✅ Extracted {len(extracted_text)} characters\\n")
                    self.flyer_results.insert(tk.END, f"Text: {extracted_text[:200]}{'...' if len(extracted_text) > 200 else ''}\\n\\n")
                except Exception as e:
                    self.flyer_results.insert(tk.END, f"❌ Text extraction failed: {str(e)}\\n\\n")
            
            # Generate Gujarati captions
            if self.generate_captions_var.get() and extracted_text:
                self.flyer_results.insert(tk.END, "🎨 Generating Gujarati captions...\\n")
                try:
                    from dubber.image_processor import generate_gujarati_captions
                    captions = generate_gujarati_captions(extracted_text, gemini_key)
                    if isinstance(captions, dict) and "error" not in captions:
                        self.flyer_results.insert(tk.END, "✅ Generated captions for all platforms\\n")
                        for platform, caption in captions.items():
                            self.flyer_results.insert(tk.END, f"  {platform.title()}: {caption[:100]}{'...' if len(caption) > 100 else ''}\\n")
                    else:
                        self.flyer_results.insert(tk.END, f"❌ Caption generation failed: {captions}\\n")
                    self.flyer_results.insert(tk.END, "\\n")
                except Exception as e:
                    self.flyer_results.insert(tk.END, f"❌ Caption generation failed: {str(e)}\\n\\n")
            
            # Generate teaser content
            if self.generate_teaser_var.get() and extracted_text:
                self.flyer_results.insert(tk.END, "🎬 Creating teaser content...\\n")
                try:
                    from dubber.image_processor import generate_teaser_content
                    teaser = generate_teaser_content(extracted_text, captions, gemini_key)
                    if isinstance(teaser, dict) and "error" not in teaser:
                        self.flyer_results.insert(tk.END, "✅ Generated teaser content\\n")
                        for key, value in teaser.items():
                            self.flyer_results.insert(tk.END, f"  {key.replace('_', ' ').title()}: {value}\\n")
                    else:
                        self.flyer_results.insert(tk.END, f"❌ Teaser generation failed: {teaser}\\n")
                    self.flyer_results.insert(tk.END, "\\n")
                except Exception as e:
                    self.flyer_results.insert(tk.END, f"❌ Teaser generation failed: {str(e)}\\n\\n")
            
            self.flyer_results.insert(tk.END, "🎉 Processing complete!\\n")
            
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
                
                self.flyer_results.insert(tk.END, f"💾 Results saved to {workspace_dir}/ folder\\n")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process flyer: {str(e)}")
            self.flyer_results.insert(tk.END, f"❌ Error: {str(e)}\\n")'''

# Replace the method
content = content.replace(old_process_method, new_process_method)

# Add the missing import for json at the top
if "import json" not in content:
    # Find the imports section and add json import
    imports_end = content.find("from dubber import (")
    if imports_end != -1:
        content = content[:imports_end] + "import json\nimport os\n" + content[imports_end:]

# Write the updated content
with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Updated flyer processing with real functionality!")
print("  - Added OCR text extraction")
print("  - Added Gujarati caption generation")
print("  - Added teaser content generation")
print("  - Added result saving to workspace")
print("  - Uses Gemini Vision API for processing")
