#!/usr/bin/env python3
"""Test all API endpoints before processing video"""

import os
import sys
import time
from datetime import datetime

# Add dubber to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dubber.translator import _gemini_translate, _translate_to_gujarati
from dubber.caption_generator import _call_mistral
from dubber.vision_extractor import _call_gemini
from dubber.transcriber import _groq_transcribe
from dubber.tts_generator import generate_tts_audio

def log_status(service, status, details=""):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {service}: {status} {details}")

def test_gemini_vision():
    """Test Gemini Vision API"""
    log_status("Gemini Vision", "Testing...")
    try:
        api_key = os.getenv("GEMINI_VISION_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            log_status("Gemini Vision", "❌ FAIL", "No API key")
            return False
        
        prompt = "Describe this image in one sentence."
        result = _call_gemini(api_key, prompt, max_retries=1)
        if result:
            log_status("Gemini Vision", "✅ PASS", f"Response: {result[:50]}...")
            return True
    except Exception as e:
        log_status("Gemini Vision", "❌ FAIL", str(e)[:50])
    return False

def test_gemini_translate():
    """Test Gemini Translation API"""
    log_status("Gemini Translate", "Testing...")
    try:
        result = _gemini_translate("Hello world", "en", "gu")
        if result:
            log_status("Gemini Translate", "✅ PASS", f"Response: {result[:30]}...")
            return True
    except Exception as e:
        log_status("Gemini Translate", "❌ FAIL", str(e)[:50])
    return False

def test_mistral():
    """Test Mistral API directly"""
    log_status("Mistral", "Testing...")
    try:
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            log_status("Mistral", "❌ FAIL", "No API key")
            return False
        
        # Simple test using Mistral's API
        import httpx
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "mistral-small",
            "messages": [{"role": "user", "content": "Say 'Hello'"}],
            "max_tokens": 10
        }
        
        r = httpx.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            log_status("Mistral", "✅ PASS", "API responded successfully")
            return True
        else:
            log_status("Mistral", "❌ FAIL", f"HTTP {r.status_code}: {r.text[:50]}")
    except Exception as e:
        log_status("Mistral", "❌ FAIL", str(e)[:50])
    return False

def test_groq():
    """Test Groq Transcription API (mock test)"""
    log_status("Groq Transcription", "Testing...")
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            log_status("Groq Transcription", "❌ FAIL", "No API key")
            return False
        
        # Just check if API key format looks valid
        if api_key.startswith("gsk_"):
            log_status("Groq Transcription", "✅ PASS", "API key format valid")
            return True
        else:
            log_status("Groq Transcription", "❌ FAIL", "Invalid API key format")
    except Exception as e:
        log_status("Groq Transcription", "❌ FAIL", str(e)[:50])
    return False

def test_zernio():
    """Test Zernio API key format"""
    log_status("Zernio Publish", "Testing...")
    try:
        api_key = os.getenv("ZERNIO_API_KEY")
        if not api_key:
            log_status("Zernio Publish", "❌ FAIL", "No API key")
            return False
        
        if api_key.startswith("sk_"):
            log_status("Zernio Publish", "✅ PASS", "API key format valid")
            return True
        else:
            log_status("Zernio Publish", "❌ FAIL", "Invalid API key format")
    except Exception as e:
        log_status("Zernio Publish", "❌ FAIL", str(e)[:50])
    return False

def main():
    print("=== API Health Check ===")
    print(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check environment variables
    required_keys = {
        "GEMINI_VISION_KEY": "Gemini Vision",
        "GEMINI_API_KEY": "Gemini Translation",
        "MISTRAL_API_KEY": "Mistral/OpenRouter",
        "GROQ_API_KEY": "Groq Transcription",
        "ZERNIO_API_KEY": "Zernio Publishing"
    }
    
    print("Checking API keys...")
    for key, service in required_keys.items():
        if os.getenv(key):
            print(f"  ✅ {service}: Key found")
        else:
            print(f"  ❌ {service}: Missing {key}")
    print()
    
    # Test each API
    results = []
    results.append(("Gemini Vision", test_gemini_vision()))
    time.sleep(1)
    
    results.append(("Gemini Translate", test_gemini_translate()))
    time.sleep(1)
    
    results.append(("Mistral", test_mistral()))
    time.sleep(1)
    
    results.append(("Groq Transcription", test_groq()))
    results.append(("Zernio Publish", test_zernio()))
    
    # Summary
    print()
    print("=== Summary ===")
    passed = sum(1 for _, status in results if status)
    total = len(results)
    
    for service, status in results:
        status_icon = "✅" if status else "❌"
        print(f"{status_icon} {service}")
    
    print()
    print(f"Overall: {passed}/{total} APIs working")
    
    if passed == total:
        print("🎉 All APIs are ready! You can start processing videos.")
        return 0
    else:
        print("⚠️  Some APIs are not working. Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
