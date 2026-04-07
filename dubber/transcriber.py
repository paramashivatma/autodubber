import os, json, subprocess
import httpx
from .config import get_groq_api_key
from .utils import log, track_api_call, track_api_success

GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3"
MAX_FILE_MB = 25  # Groq limit

# Post-processing dictionary for common transcription errors
# Maps incorrect words (lowercase) to correct words
TRANSCRIPTION_FIXES = {
    # Sanskrit terms
    "avyakta": "avyakta",
    "object": "avyakta",  # Common mishearing of avyakta
    "samadhi": "Samadhi",
    "turiyatita": "Turiyatita",
    "brahman": "Brahman",
    "atman": "Atman",
    "nirvikalpa": "Nirvikalpa",
    # Proper names
    "lithyananda": "Nithyananda",
    "nithyananda": "Nithyananda",
    "kailasa": "KAILASA",
    "paramashiva": "Paramashivam",
    # Common words
    "uncertainity": "uncertainty",
    "avyaktha": "avyakta",
}

# File to store user-approved transcription fixes
TRANSCRIPTION_FIXES_FILE = os.path.join(
    os.path.expanduser("~"), ".video_dubber_transcription_fixes.json"
)


def _load_user_fixes():
    """Load user-approved transcription fixes from file."""
    try:
        if os.path.exists(TRANSCRIPTION_FIXES_FILE):
            with open(TRANSCRIPTION_FIXES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_user_fixes(fixes):
    """Save user-approved transcription fixes to file."""
    try:
        with open(TRANSCRIPTION_FIXES_FILE, "w", encoding="utf-8") as f:
            json.dump(fixes, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log("TRANSCRIBE", f"Failed to save transcription fixes: {e}")


def _get_all_fixes():
    """Get combined fixes from built-in and user-approved."""
    all_fixes = dict(TRANSCRIPTION_FIXES)
    all_fixes.update(_load_user_fixes())
    return all_fixes


def _apply_transcription_fixes(text):
    """Apply post-processing fixes to transcription text."""
    if not text:
        return text

    all_fixes = _get_all_fixes()
    words = text.split()
    fixed_words = []
    for word in words:
        # Check if word (lowercase) is in fixes
        word_lower = word.lower().strip(".,!?;:")
        if word_lower in all_fixes:
            # Preserve original capitalization pattern
            fixed = all_fixes[word_lower]
            if word[0].isupper():
                fixed = fixed.capitalize()
            fixed_words.append(fixed)
        else:
            fixed_words.append(word)

    return " ".join(fixed_words)


def _suggest_fix(original_word, suggested_word):
    """Suggest a transcription fix for user approval."""
    user_fixes = _load_user_fixes()

    # Check if already in built-in or user fixes
    word_lower = original_word.lower()
    if word_lower in TRANSCRIPTION_FIXES or word_lower in user_fixes:
        return False  # Already have a fix for this word

    # Add to pending suggestions
    pending_file = TRANSCRIPTION_FIXES_FILE.replace(".json", "_pending.json")
    pending = {}
    if os.path.exists(pending_file):
        try:
            with open(pending_file, "r", encoding="utf-8") as f:
                pending = json.load(f)
        except Exception:
            pass

    if word_lower not in pending:
        pending[word_lower] = suggested_word
        try:
            with open(pending_file, "w", encoding="utf-8") as f:
                json.dump(pending, f, indent=2, ensure_ascii=False)
            log(
                "TRANSCRIBE", f"  Suggested fix: '{original_word}' → '{suggested_word}'"
            )
            return True
        except Exception:
            pass

    return False


def get_pending_fixes():
    """Get pending transcription fixes for user review."""
    pending_file = TRANSCRIPTION_FIXES_FILE.replace(".json", "_pending.json")
    if os.path.exists(pending_file):
        try:
            with open(pending_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def approve_fixes(fixes_to_approve):
    """Approve pending transcription fixes and add to permanent dictionary."""
    pending = get_pending_fixes()
    user_fixes = _load_user_fixes()

    approved_count = 0
    for word, correction in fixes_to_approve.items():
        if word in pending:
            user_fixes[word.lower()] = correction
            approved_count += 1

    if approved_count > 0:
        _save_user_fixes(user_fixes)
        # Clear approved items from pending
        pending_file = TRANSCRIPTION_FIXES_FILE.replace(".json", "_pending.json")
        remaining = {k: v for k, v in pending.items() if k not in fixes_to_approve}
        try:
            with open(pending_file, "w", encoding="utf-8") as f:
                json.dump(remaining, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        log("TRANSCRIBE", f"Approved {approved_count} transcription fixes")

    return approved_count


def clear_pending_fixes():
    """Clear all pending transcription fixes."""
    pending_file = TRANSCRIPTION_FIXES_FILE.replace(".json", "_pending.json")
    try:
        if os.path.exists(pending_file):
            os.remove(pending_file)
    except Exception:
        pass


def _extract_audio(video_path, out_wav):
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "wav",
            out_wav,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError(
            f"Audio extraction failed for {video_path}: {r.stderr[-400:]}"
        )


def _split_audio(wav_path, output_dir, chunk_sec=600):
    """Split audio into chunks if over 25MB."""
    size_mb = os.path.getsize(wav_path) / (1024 * 1024)
    if size_mb <= MAX_FILE_MB:
        return [wav_path]
    chunks = []
    i = 0
    while True:
        chunk_path = os.path.join(output_dir, f"chunk_{i:03d}.wav")
        r = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                wav_path,
                "-ss",
                str(i * chunk_sec),
                "-t",
                str(chunk_sec),
                "-ar",
                "16000",
                "-ac",
                "1",
                chunk_path,
            ],
            capture_output=True,
        )
        if r.returncode != 0 or not os.path.exists(chunk_path):
            break
        if os.path.getsize(chunk_path) < 1000:
            break
        chunks.append(chunk_path)
        i += 1
    return chunks


def _transcribe_chunk(api_key, audio_path, language=None):
    track_api_call("groq")
    headers = {"Authorization": f"Bearer {api_key}"}

    with open(audio_path, "rb") as f:
        data = f.read()

    # Build multipart manually — Groq is strict about field format
    fields = [
        ("model", (None, GROQ_MODEL)),
        ("response_format", (None, "verbose_json")),
        ("temperature", (None, "0.0")),
    ]
    if language:
        fields.append(("language", (None, language)))

    fields.append(("file", (os.path.basename(audio_path), data, "audio/wav")))

    r = httpx.post(GROQ_API_URL, headers=headers, files=fields, timeout=120)
    if r.is_success:
        track_api_success("groq")
    if not r.is_success:
        log("TRANSCRIBE", f"Groq error body: {r.text[:300]}")
        r.raise_for_status()
    return r.json()


def _groq_transcribe(api_key, audio_path, language, output_dir):
    chunks = _split_audio(audio_path, output_dir)
    if not chunks:
        raise RuntimeError("Audio chunking produced no chunks for Groq transcription.")
    all_segments = []
    time_offset = 0.0
    detected_lang = None

    for chunk_path in chunks:
        log("TRANSCRIBE", f"Groq transcribing: {os.path.basename(chunk_path)} ...")
        result = _transcribe_chunk(api_key, chunk_path, language)
        detected_lang = result.get("language", language)
        for seg in result.get("segments", []):
            # Apply transcription fixes to correct common errors
            fixed_text = _apply_transcription_fixes(seg["text"].strip())
            all_segments.append(
                {
                    "id": seg.get("id", len(all_segments)),
                    "start": round(seg["start"] + time_offset, 3),
                    "end": round(seg["end"] + time_offset, 3),
                    "text": fixed_text,
                }
            )
        # Advance offset by last segment end
        segs = result.get("segments", [])
        if segs:
            time_offset += segs[-1]["end"]

    return all_segments, detected_lang


def _local_transcribe(audio_path, language, model_size, output_dir):
    lang_code = language if language and language != "auto" else None

    try:
        from faster_whisper import WhisperModel

        log("TRANSCRIBE", f"Local Whisper (faster-whisper): {model_size}")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        fw_segments, info = model.transcribe(
            audio_path, language=lang_code, beam_size=5, vad_filter=True
        )
        detected = getattr(info, "language", language)
        segments = []
        for i, seg in enumerate(fw_segments):
            text = (getattr(seg, "text", "") or "").strip()
            if not text:
                continue
            # Apply transcription fixes to correct common errors
            fixed_text = _apply_transcription_fixes(text)
            segments.append(
                {
                    "id": i,
                    "start": round(float(seg.start), 3),
                    "end": round(float(seg.end), 3),
                    "text": fixed_text,
                }
            )
        log(
            "TRANSCRIBE",
            f"Lang: {detected} p={getattr(info, 'language_probability', 0):.2f}",
        )
        return segments, detected
    except Exception as e:
        raise RuntimeError(
            "Local transcription failed. Set GROQ_API_KEY for cloud transcription "
            "or install faster-whisper (pip install faster-whisper)."
        ) from e


def transcribe_audio(
    video_path, output_dir, model_size="large", language="auto", groq_api_key=None
):
    os.makedirs(output_dir, exist_ok=True)
    wav_path = os.path.join(output_dir, "audio.wav")
    _extract_audio(video_path, wav_path)

    groq_key = get_groq_api_key(groq_api_key)

    if groq_key:
        log("TRANSCRIBE", f"Using Groq whisper-large-v3 (lang={language}) ...")
        try:
            lang_code = None if language in ("auto", None) else language
            segments, detected = _groq_transcribe(
                groq_key, wav_path, lang_code, output_dir
            )
            log("TRANSCRIBE", f"Lang detected: {detected}")
        except Exception as e:
            log("TRANSCRIBE", f"Groq failed: {e} — falling back to local Whisper ...")
            segments, detected = _local_transcribe(
                wav_path, language, model_size, output_dir
            )
    else:
        log("TRANSCRIBE", "No GROQ_API_KEY — using local Whisper ...")
        segments, detected = _local_transcribe(
            wav_path, language, model_size, output_dir
        )

    out_path = os.path.join(output_dir, "transcript.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    log("TRANSCRIBE", f"{len(segments)} segments -> {out_path}")
    return segments
