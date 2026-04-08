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
    "lithuania": "Nithyananda",
    "lithuanian": "Nithyananda",
    "nithyananda": "Nithyananda",
    "kailasa": "KAILASA",
    "paramashiva": "Paramashivam",
    # Common words
    "uncertainity": "uncertainty",
    "avyaktha": "avyakta",
}

# Known words and their common mishearings for auto-learn pattern matching
# Format: correct_word -> list of common mishearings
KNOWN_WORDS_MISHEARINGS = {
    # Sanskrit terms
    "avyakta": ["object", "obstruct", "abject", "a vyakta", "avyak tha"],
    "samadhi": ["somebody", "sam ahi", "some ahi", "sama dhi"],
    "turiyatita": ["turkey tita", "turi ya tita", "turi ya teeta"],
    "brahman": ["brahmin", "broad man", "bra man", "brah man"],
    "atman": ["at man", "adman", "atman", "at man"],
    "nirvikalpa": ["near vikalpa", "nir vikalpa", "near vikal fa"],
    "paramashiva": ["parama shiva", "parama sheva", "parama sheeba"],
    "paramashivam": ["parama shivam", "parama shevam", "parama sheebam"],
    # Proper names
    "nithyananda": [
        "lithyananda",
        "lithuania",
        "lithuanian",
        "nithya nanda",
        "with yananda",
        "nit ya nanda",
        "nith yananda",
    ],
    "kailasa": ["kyle asa", "kai lasa", "kai lasa", "ky lasa"],
    "kailaas": ["kyle as", "kai las", "kai laas"],
    "spH": ["s p h", "sph", "s. p. h."],
    "bhagavan": ["bhagwan", "bhagawaan", "bhag van"],
    "paramashivatma": ["parama shivatma", "parama shiva atma"],
}

# File to store user-approved transcription fixes
TRANSCRIPTION_FIXES_FILE = os.path.join(
    os.path.expanduser("~"), ".video_dubber_transcription_fixes.json"
)


def _levenshtein_distance(s1, s2):
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def _similar_words(word1, word2, threshold=0.75):
    """Check if two words are similar using Levenshtein distance."""
    if len(word1) < 3 or len(word2) < 3:
        return False

    word1_lower = word1.lower()
    word2_lower = word2.lower()

    # Exact match after lowercase
    if word1_lower == word2_lower:
        return True

    # Check if one contains the other (for compound words)
    if word2_lower in word1_lower or word1_lower in word2_lower:
        # Only if the shorter word is at least 60% of the longer word
        shorter = min(len(word1_lower), len(word2_lower))
        longer = max(len(word1_lower), len(word2_lower))
        if shorter / longer >= 0.6:
            return True

    # Levenshtein distance ratio
    distance = _levenshtein_distance(word1_lower, word2_lower)
    max_len = max(len(word1_lower), len(word2_lower))
    similarity = 1 - (distance / max_len)

    return similarity >= threshold


def _detect_potential_errors(transcribed_text):
    """
    Detect potential transcription errors using pattern matching.
    Returns list of (original_word, suggested_correction) tuples.
    """
    if not transcribed_text:
        return []

    suggestions = []
    words = transcribed_text.split()
    all_fixes = _get_all_fixes()

    for word in words:
        word_lower = word.lower().strip(".,!?;:")

        # Skip if already in fixes
        if word_lower in all_fixes:
            continue

        # Skip very short words
        if len(word_lower) < 4:
            continue

        # Check each known word's common mishearings
        for correct_word, mishearings in KNOWN_WORDS_MISHEARINGS.items():
            # Check exact mishearing match
            for mishearing in mishearings:
                if word_lower == mishearing.lower():
                    suggestions.append((word, correct_word))
                    break
            else:
                # Check similarity if no exact match
                if _similar_words(word_lower, correct_word):
                    # Make sure it's not already suggested
                    if not any(s[1] == correct_word for s in suggestions):
                        suggestions.append((word, correct_word))

    return suggestions


def _auto_learn_from_transcription(transcribed_text):
    """
    Auto-learn potential transcription errors and add to pending fixes.
    Returns number of new suggestions added.
    """
    if not transcribed_text:
        return 0

    suggestions = _detect_potential_errors(transcribed_text)
    added_count = 0

    for original, correction in suggestions:
        if _suggest_fix(original, correction):
            added_count += 1

    if added_count > 0:
        log("TRANSCRIBE", f"Auto-learned {added_count} potential transcription fix(es)")

    return added_count


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

    # Auto-learn potential transcription errors
    log("TRANSCRIBE", "Running auto-learn for transcription fixes...")
    full_text = " ".join(seg.get("text", "") for seg in segments)
    _auto_learn_from_transcription(full_text)

    out_path = os.path.join(output_dir, "transcript.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    log("TRANSCRIBE", f"{len(segments)} segments -> {out_path}")
    return segments
