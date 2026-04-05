import os, asyncio, time, re, json
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
    "default": ["en-IN-NeerjaNeural"],
}

# Languages supported by OpenVoice V2
OPENVOICE_LANGUAGES = {"en", "es", "fr", "zh", "ja", "ko"}

_loop = None


def _run_async(coro):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    try:
        return _loop.run_until_complete(coro)
    except Exception:
        _loop.close()
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        return _loop.run_until_complete(coro)


async def _synthesize(text, voice, path):
    await edge_tts.Communicate(text, voice).save(path)


def _sanitize_text(text):
    """Clean text for TTS synthesis - remove problematic characters."""
    if not text:
        return "..."

    # Remove control characters except newlines and tabs
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Replace multiple spaces with single space
    text = re.sub(r"\s+", " ", text)

    # Remove excessive punctuation
    text = re.sub(r"([.!?])\1+", r"\1", text)

    # Ensure text is not empty
    text = text.strip() or "..."

    # Limit text length (Edge TTS has limits)
    if len(text) > 5000:
        text = text[:4997] + "..."

    return text


def _extract_reference_audio(video_path, output_path, duration=10):
    """Extract a clean reference audio segment from source video for voice cloning."""
    import subprocess

    try:
        # Extract first 10 seconds of audio
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-t",
                str(duration),
                "-ar",
                "22050",
                "-ac",
                "1",
                "-f",
                "wav",
                output_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            log("TTS", f"  Reference audio extracted: {output_path}")
            return output_path
    except Exception as e:
        log("TTS", f"  Reference audio extraction failed: {e}")
    return None


def _get_openvoice_model(model_dir=None):
    """Initialize OpenVoice model, downloading if needed."""
    if model_dir is None:
        model_dir = os.path.join(
            os.path.expanduser("~"), ".openvoice", "checkpoints_v2"
        )

    try:
        from openvoice import se_extractor
        from openvoice.api import BaseSpeakerTTS, ToneColorConverter

        # Check if models exist
        if not os.path.exists(model_dir):
            log("TTS", "  Downloading OpenVoice V2 models...")
            os.makedirs(model_dir, exist_ok=True)
            # Models will be downloaded on first use
            log("TTS", "  Models will download automatically on first use (~300MB)")

        return model_dir, BaseSpeakerTTS, ToneColorConverter, se_extractor
    except ImportError:
        log("TTS", "  OpenVoice not installed. Install with: pip install openvoice")
        return None, None, None, None


def _synthesize_openvoice(
    text, reference_audio, output_path, language="en", model_dir=None
):
    """Synthesize speech using OpenVoice with cloned voice."""
    try:
        from openvoice.api import BaseSpeakerTTS, ToneColorConverter
        from openvoice import se_extractor

        if model_dir is None:
            model_dir = os.path.join(
                os.path.expanduser("~"), ".openvoice", "checkpoints_v2"
            )

        os.makedirs(model_dir, exist_ok=True)

        # Initialize base TTS
        base_tts_path = os.path.join(model_dir, "base_speakers")
        if not os.path.exists(base_tts_path):
            log("TTS", "  Downloading base speaker models...")
            # Download models programmatically
            import urllib.request
            import zipfile

            # OpenVoice V2 models
            model_url = "https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2/converter.zip"
            zip_path = os.path.join(model_dir, "converter.zip")

            if not os.path.exists(zip_path):
                urllib.request.urlretrieve(model_url, zip_path)
                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(model_dir)

        # Initialize tone color converter
        converter = ToneColorConverter(
            os.path.join(model_dir, "converter", "config.json"),
            device="cpu",
        )
        converter.load_ckpt(os.path.join(model_dir, "converter", "checkpoint.pth"))

        # Extract speaker embedding from reference audio
        ref_embed = se_extractor.get_wav_np(reference_audio)[0]
        ref_embed = ref_embed.unsqueeze(0)

        # Get speaker embedding
        target_se, audio_name = se_extractor._extract_sequential(
            reference_audio, model_dir, device="cpu"
        )

        # Generate speech with base speaker
        base_tts = BaseSpeakerTTS(
            os.path.join(model_dir, "base_speakers", "config.json"),
            device="cpu",
        )
        base_tts.load_ckpt(os.path.join(model_dir, "base_speakers", "checkpoint.pth"))

        # Synthesize with cloned voice
        base_tts.tts(text, output_path, speaker=language, sdp_ratio=0.2)

        # Apply tone color conversion
        converter.convert(
            audio_ref=ref_embed,
            audio_gen=output_path,
            audio_out=output_path,
        )

        if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            return True
        return False

    except Exception as e:
        log("TTS", f"  OpenVoice synthesis failed: {e}")
        return False


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


def generate_tts_audio(
    segments,
    voice="gu-IN-NiranjanNeural",
    output_dir="workspace",
    clone_voice=False,
    reference_audio=None,
    source_video=None,
):
    """
    Generate TTS audio for each segment.

    Args:
        segments: List of segment dicts with 'translated' or 'text'
        voice: Edge TTS voice ID (e.g., "gu-IN-NiranjanNeural")
        output_dir: Output directory
        clone_voice: If True, use OpenVoice for voice cloning
        reference_audio: Path to reference audio for cloning (optional)
        source_video: Path to source video (used to extract reference if not provided)
    """
    clips_dir = os.path.join(output_dir, "tts_clips")
    os.makedirs(clips_dir, exist_ok=True)
    log("TTS", f"Voice: {voice}  |  {len(segments)} segments")

    # Determine target language from voice
    lang_code = voice.split("-")[0] if "-" in voice else "en"
    use_openvoice = clone_voice and lang_code in OPENVOICE_LANGUAGES

    if use_openvoice:
        log("TTS", "  Using OpenVoice for voice cloning")

        # Extract reference audio if not provided
        if not reference_audio and source_video:
            ref_path = os.path.join(output_dir, "reference_voice.wav")
            reference_audio = _extract_reference_audio(source_video, ref_path)

        if not reference_audio or not os.path.exists(reference_audio):
            log("TTS", "  Reference audio not available, falling back to Edge TTS")
            use_openvoice = False
        else:
            log("TTS", f"  Reference audio: {reference_audio}")

    results = []
    skipped = []
    failed_segments = []

    # Get fallback voices
    voices = _get_fallback_voices(voice)
    log("TTS", f"Available voices: {voices}")

    for idx, seg in enumerate(segments):
        seg_id = seg["id"]
        raw_text = (seg.get("translated") or seg.get("text", "")).strip()
        text = _sanitize_text(raw_text)
        clip = os.path.join(clips_dir, f"clip_{seg_id:04d}.wav")

        log("TTS", f"[{idx + 1}/{len(segments)}] seg#{seg_id}: {text[:70]}")

        success = False
        last_error = None

        # Try OpenVoice first if enabled
        if use_openvoice:
            try:
                if _synthesize_openvoice(
                    text, reference_audio, clip, language=lang_code
                ):
                    success = True
                    log("TTS", f"  OpenVoice synthesis successful")
                else:
                    log("TTS", "  OpenVoice failed, falling back to Edge TTS")
            except Exception as e:
                log("TTS", f"  OpenVoice error: {e}, falling back to Edge TTS")

        # Fall back to Edge TTS
        if not success:
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
                                log(
                                    "TTS",
                                    f"  Success with fallback voice: {current_voice}",
                                )
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
                            delay = 2**attempt
                            log("TTS", f"  Retrying in {delay}s...")
                            time.sleep(delay)

                if success:
                    break

        if not success:
            log("TTS", f"  FAILED seg#{seg_id} after all attempts and fallbacks")
            log("TTS", f"     Last error: {last_error}")
            log("TTS", f"     Text: {text[:100]}")
            skipped.append(seg_id)
            failed_segments.append(
                {"seg_id": seg_id, "text": text, "error": str(last_error)}
            )
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
            with open(failed_path, "w", encoding="utf-8") as f:
                json.dump(failed_segments, f, ensure_ascii=False, indent=2)
            log("TTS", f"Failed segments saved to: {failed_path}")
        except Exception as e:
            log("TTS", f"Could not save failed segments: {e}")

    return results
