import os, asyncio, time
import edge_tts
from pydub import AudioSegment
from .utils import log

def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

async def _synthesize(text, voice, path):
    await edge_tts.Communicate(text, voice).save(path)

def generate_tts_audio(segments, voice="gu-IN-NiranjanNeural", output_dir="workspace"):
    clips_dir = os.path.join(output_dir, "tts_clips")
    os.makedirs(clips_dir, exist_ok=True)
    log("TTS", f"Voice: {voice}  |  {len(segments)} segments")
    results = []
    for idx, seg in enumerate(segments):
        seg_id = seg["id"]
        text   = (seg.get("translated") or seg.get("text","")).strip() or "..."
        clip   = os.path.join(clips_dir, f"clip_{seg_id:04d}.wav")
        log("TTS", f"[{idx+1}/{len(segments)}] seg#{seg_id}: {text[:70]}")
        for attempt in range(1, 4):
            try:
                _run_async(_synthesize(text, voice, clip))
                break
            except Exception as e:
                log("TTS", f"  Attempt {attempt} failed: {e}")
                if attempt < 3:
                    time.sleep(3)
                else:
                    raise RuntimeError(f"TTS failed after 3 attempts: {e}")
        dur_ms = len(AudioSegment.from_file(clip))
        results.append({**seg, "audio_path": clip, "audio_dur_ms": dur_ms})
        log("TTS", f"  -> {dur_ms}ms")
    return results