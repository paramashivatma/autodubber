#!/usr/bin/env python3
"""Check available Gemini models"""

import os
from google import genai

api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("No Gemini API key found")
    exit(1)

client = genai.Client(api_key=api_key)

print("Available Gemini models:")
for model in client.models.list():
    if 'generateContent' in model.supported_generation_methods:
        print(f"  {model.name}")
