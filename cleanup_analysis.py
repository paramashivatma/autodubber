#!/usr/bin/env python3
"""Analysis of .env keys and Whisper model usage"""

# ACTUALLY USED KEYS (from grep search)
used_keys = {
    # Core functionality
    "GOOGLE_SHEET_ID": "Google Sheets API - Sheet tracking",
    "GROQ_API_KEY": "Groq Transcription API - Primary transcription",
    "GEMINI_API_KEY": "Gemini Translation API - Video translation",
    "ZERNIO_API_KEY": "Zernio Publishing API - Social media publishing",
    
    # Caption generation
    "OPENROUTER_API_KEY": "OpenRouter/Mistral API - Caption generation (fallback)",
    "MISTRAL_API_KEY": "Mistral API - Caption generation (direct)",
    
    # Vision analysis
    "GEMINI_VISION_KEY": "Gemini Vision API - Video content analysis",
    
    # Dubbing settings
    "DUB_VOICE": "TTS voice selection - Used in GUI",
    "DUB_SOURCE_LANG": "Source language - Used in GUI",
    "DUB_TARGET_LANG": "Target language - Used in GUI",
    "DUB_WHISPER_MODEL": "Whisper model - NOT USED (GUI overrides)",
}

# UNUSED KEYS
unused_keys = {
    "SOURCE_CHANNEL": "Telegram bot - Not used in current codebase",
    "INPUT_VIDEO_PATH": "Legacy - Not used",
    "GOOGLE_SERVICE_ACCOUNT_JSON": "Hardcoded as 'credentials.json'",
    "SEMI_AUTO_PUBLISH": "Auto publish script - Not in main app",
    "MAX_RETRIES": "Auto publish script - Not in main app",
    "ARCHIVE_DIR": "Auto publish script - Not in main app",
    "DAILY_LOG_DIR": "Auto publish script - Not in main app",
    "TELEGRAM_BOT_TOKEN": "Telegram bot - Not used in current codebase",
    "TELEGRAM_CHAT_ID": "Telegram bot - Not used in current codebase",
    "GEMINI_DAILY_LIMIT": "Auto publish script - Not in main app",
    "ARCHIVE_RETENTION_DAYS": "Auto publish script - Not in main app",
    "MIN_DISK_GB": "Auto publish script - Not in main app",
    "GEMINI_CAPTION_KEY": "Duplicate of GEMINI_API_KEY",
    "NVIDIA_API_KEY": "Not used anywhere in codebase",
}

# WHISPER MODEL ANALYSIS
whisper_analysis = """
WHISPER MODEL SELECTOR STATUS: NEEDED and FUNCTIONAL

1. GUI has Whisper model selector (app.py line 202-204)
   - Default value: "large"
   - Options: ["tiny","base","small","medium","large"]
   - User can change selection

2. Model is ACTUALLY USED in transcription:
   - transcribe_audio() receives model_size parameter (app.py line 76)
   - _local_transcribe() uses the model (transcriber.py line 92)
   - Falls back to local Whisper when Groq fails

3. Current flow:
   - Primary: Groq API (whisper-large-v3) - ignores GUI setting
   - Fallback: Local Whisper - USES GUI setting

4. Recommendation: KEEP THE SELECTOR
   - It's functional and used as fallback
   - Users may want different local models for speed/accuracy
   - Only affects local Whisper, not Groq API
"""

def print_analysis():
    print("=== ENV KEYS ANALYSIS ===\n")
    
    print("✅ KEYS IN USE:")
    for key, desc in used_keys.items():
        print(f"  {key}: {desc}")
    
    print(f"\n❌ UNUSED KEYS ({len(unused_keys)}):")
    for key, desc in unused_keys.items():
        print(f"  {key}: {desc}")
    
    print(f"\n{whisper_analysis}")

if __name__ == "__main__":
    print_analysis()
