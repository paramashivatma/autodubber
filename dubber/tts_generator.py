import os, asyncio, time, re
import edge_tts
from pydub import AudioSegment
from .utils import log

# Fallback voices for different languages
FALLBACK_VOICES = {
    "gu-IN": ["gu-IN-NiranjanNeural", "gu-IN-DhwaniNeural"],
    "hi-IN": ["hi-IN-MadhurNeural", "hi-IN-SwaraNeural"],
    "ta-IN": ["ta-IN-PallaviNeural", "ta-IN-ValluvarNeural"],
    "te-IN": ["te-IN-MohanNeural", "te-IN-ShrutiNeural"],
    "kn-IN": ["kn-IN-GaganNeural", "kn-IN-SapnaNeural"],
    "ml-IN": ["ml-IN-MidhunNeural", "ml-IN-SobhanaNeural"],
    "bn-IN": ["bn-IN-BashkarNeural", "bn-IN-TanishaaNeural"],
    "en-IN": ["en-IN-NeerjaNeural", "en-IN-PrabhatNeural"],
    "default": ["en-IN-NeerjaNeural"]
}

def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

async def _synthesize(text, voice, path):
    await edge_tts.Communicate(text, voice).save(path)

def _sanitize_text(text):
    """Clean text for TTS synthesis - remove problematic characters."""
    if not text:
        return "..."
    
    # Remove control characters except newlines and tabs
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Remove excessive punctuation
    text = re.sub(r'([.!?])\1+', r'\1', text)
    
    # Ensure text is not empty
    text = text.strip() or "..."
    
    # Limit text length (Edge TTS has limits)
    if len(text) > 5000:
        text = text[:4997] + "..."
    
    return text

def _get_fallback_voices(primary_voice):
    """Get list of fallback voices for a given primary voice."""
    # Extract language code from voice (e.g., "gu-IN-NiranjanNeural" -> "gu-IN")
    lang_code = "-".join(primary_voice.split("-")[:2])
    
    # Get fallback voices for this language
    fallbacks = FALLBACK_VOICES.get(lang_code, FALLBACK_VOICES["default"])
    
    # Ensure primary voice is first in list
    voices = [primary_voice]
    for v in fallbacks:
        if v != primary_voice:
            voices.append(v)
    
    return voices

def generate_tts_audio(segments, voice="gu-IN-NiranjanNeural", output_dir="workspace"):
    clips_dir = os.path.join(output_dir, "tts_clips")
    os.makedirs(clips_dir, exist_ok=True)
    log("TTS", f"Voice: {voice}  |  {len(segments)} segments")
    
    results = []
    skipped = []
    failed_segments = []  # Track failed segments for retry
    
    # Get fallback voices
    voices = _get_fallback_voices(voice)
    log("TTS", f"Available voices: {voices}")
    
    for idx, seg in enumerate(segments):
        seg_id = seg["id"]
        raw_text = (seg.get("translated") or seg.get("text","")).strip()
        text = _sanitize_text(raw_text)
        clip = os.path.join(clips_dir, f"clip_{seg_id:04d}.wav")
        
        log("TTS", f"[{idx+1}/{len(segments)}] seg#{seg_id}: {text[:70]}")
        
        success = False
        last_error = None
        
        # Try with each voice (primary first, then fallbacks)
        for voice_idx, current_voice in enumerate(voices):
            if voice_idx > 0:
                log("TTS", f"  Trying fallback voice: {current_voice}")
            
            # Exponential backoff: 5 attempts with increasing delays
            for attempt in range(1, 6):
                try:
                    _run_async(_synthesize(text, current_voice, clip))
                    
                    # Verify file was created
                    if os.path.exists(clip) and os.path.getsize(clip) > 100:
                        success = True
                        if voice_idx > 0:
                            log("TTS", f"  Success with fallback voice: {current_voice}")
                        break
                    else:
                        raise RuntimeError("Generated file is empty or too small")
                        
                except Exception as e:
                    last_error = e
                    error_msg = str(e)
                    
                    # Log specific error types
                    if "403" in error_msg or "Forbidden" in error_msg:
                        log("TTS", f"  Attempt {attempt}: Rate limited (403)")
                    elif "404" in error_msg or "Not Found" in error_msg:
                        log("TTS", f"  Attempt {attempt}: Voice not found (404)")
                    elif "timeout" in error_msg.lower():
                        log("TTS", f"  Attempt {attempt}: Timeout")
                    else:
                        log("TTS", f"  Attempt {attempt}: {error_msg[:100]}")
                    
                    # Exponential backoff: 2s, 4s, 8s, 16s
                    if attempt < 5:
                        delay = 2 ** attempt
                        log("TTS", f"  Retrying in {delay}s...")
                        time.sleep(delay)
            
            if success:
                break
        
        if not success:
            log("TTS", f"  FAILED seg#{seg_id} after all attempts and fallbacks")
            log("TTS", f"     Last error: {last_error}")
            log("TTS", f"     Text: {text[:100]}")
            skipped.append(seg_id)
            failed_segments.append({
                "seg_id": seg_id,
                "text": text,
                "error": str(last_error)
            })
            continue
        
        dur_ms = len(AudioSegment.from_file(clip))
        results.append({**seg, "audio_path": clip, "audio_dur_ms": dur_ms})
        log("TTS", f"  Generated {dur_ms}ms")
    
    if skipped:
        log("TTS", f"  WARNING: {len(skipped)} segments failed: {skipped}")
        log("TTS", f"Failed segments details:")
        for fs in failed_segments:
            log("TTS", f"  - seg#{fs['seg_id']}: {fs['error'][:50]}")
    
    # Save failed segments for potential retry
    if failed_segments:
        failed_path = os.path.join(output_dir, "tts_failed_segments.json")
        try:
            import json
            with open(failed_path, "w", encoding="utf-8") as f:
                json.dump(failed_segments, f, ensure_ascii=False, indent=2)
            log("TTS", f"Failed segments saved to: {failed_path}")
        except Exception as e:
            log("TTS", f"Could not save failed segments: {e}")
    
    return results