import os, json, re, subprocess
import httpx
from .config import get_deepgram_api_key
from .utils import ffprobe_duration as _ffprobe_duration, log, track_api_call, track_api_success

DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_MODEL = "nova-3"
# Deepgram accepts uploads up to ~2GB, but we keep the same chunking safety
# net we had for Groq so wav files for very long videos stream in bounded
# pieces. 100MB per request is well under Deepgram's limit and keeps a
# single HTTP call from dominating end-to-end latency.
MAX_FILE_MB = 100

# Module-level cache for faster-whisper models. Loading Whisper-large from
# disk costs ~5–10s per instantiation; the dub verifier calls
# _local_transcribe once per chunk and was paying that cost 5× per run.
# Keyed by (model_size, device, compute_type) so a dub + verify in
# different sizes (rare) doesn't collide.
_WHISPER_MODEL_CACHE = {}
MIN_GAP_PROBE_SEC = 0.75
MIN_EDGE_GAP_PROBE_SEC = 0.2
MIN_PROBE_AUDIO_BYTES = 1000
PROBE_AUDIO_SAMPLE_RATE = "16000"
PROBE_AUDIO_CHANNELS = "1"
OPENING_RECOVERY_WINDOW_SEC = 12.0
OPENING_PRESERVE_WINDOW_SEC = 18.0
SANSKRIT_LANG_CODES = {"sa", "san", "sanskrit"}
SANSKRIT_TOKEN_MARKERS = {
    "atma",
    "atman",
    "brahma",
    "bhuta",
    "chinna",
    "dvaidha",
    "hite",
    "kalmasha",
    "kalmashah",
    "kshina",
    "mantra",
    "mantram",
    "moksha",
    "narayana",
    "nirvanam",
    "paramashivoham",
    "ratah",
    "sarva",
    "shloka",
    "sloka",
    "suktam",
    "svaha",
    "yatatmana",
    "yatatmanah",
    "yatendriya",
}
SCRIPTURE_OPENING_MARKERS = {
    "bhagavad",
    "gita",
    "chapter",
    "verse",
    "yoga",
    "shloka",
    "sloka",
    "translation",
}
SCRIPTURE_TRANSLATION_CUES = {
    "translation",
    "meaning",
    "commentary",
}
PROTECTED_PHRASE_PATTERNS = {
    r"\bsovereign order of kailashas nithyananda\b": "Sovereign Order of KAILASA's Nithyananda",
    r"\bsovereign order of kailasa(?:'s|s)? nithyananda\b": "Sovereign Order of KAILASA's Nithyananda",
}
NON_SPEECH_PHRASE_PATTERNS = (
    r"\bsubtitles by the amara\.org community\b",
    r"\bamara\.org\b",
)


def _looks_like_spoken_text(text):
    """Heuristic to distinguish likely speech from punctuation/noise-only output."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip(" \t\r\n-–—_")
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in NON_SPEECH_PHRASE_PATTERNS):
        return False
    if re.fullmatch(r"[^\w]+", cleaned, flags=re.UNICODE):
        return False
    tokens = re.findall(r"[^\W_]+(?:['’-][^\W_]+)?|\d+", cleaned, flags=re.UNICODE)
    if not tokens:
        return False

    meaningful = [tok for tok in tokens if sum(ch.isalnum() for ch in tok) >= 2]
    if not meaningful:
        return False

    filler_tokens = {"uh", "um", "hmm", "hm", "mm", "mmm", "ah"}
    if all(tok.lower() in filler_tokens for tok in meaningful):
        return False

    return True


def _looks_like_probe_speech(text, duration_sec=0.0):
    """Stricter speech gate for coverage probes to avoid dubbing music/noise gaps."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip(" \t\r\n-–—_")
    if not _looks_like_spoken_text(cleaned):
        return False

    normalized = re.sub(r"[^\w\s']", "", cleaned.lower(), flags=re.UNICODE).strip()
    tokens = re.findall(r"[^\W_]+(?:['’-][^\W_]+)?|\d+", cleaned, flags=re.UNICODE)
    meaningful = [tok for tok in tokens if sum(ch.isalnum() for ch in tok) >= 2]
    alnum_count = sum(ch.isalnum() for ch in cleaned)
    generic_probe_phrases = {
        "i dont know",
        "i don't know",
        "you know",
        "okay",
        "ok",
        "yeah",
        "yes",
        "no",
    }
    repetitive_interjections = {"oh", "ah", "ha", "hey"}

    if normalized in generic_probe_phrases and len(meaningful) <= 3 and duration_sec <= 2.5:
        return False
    if meaningful and all(tok.lower() in repetitive_interjections for tok in meaningful):
        return False

    if len(meaningful) >= 2:
        return True
    if alnum_count >= 6 and duration_sec >= 0.45:
        return True
    return False


def _normalize_protected_phrases(text):
    normalized = str(text or "")
    for pattern, replacement in PROTECTED_PHRASE_PATTERNS.items():
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bswayambhag(?:a|ha)\b", "Swayambhaga", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bswayambaha\b", "Swayambhaga", normalized, flags=re.IGNORECASE)
    return normalized


def _normalize_language_code(language):
    value = str(language or "").strip().lower()
    if not value:
        return ""
    if "-" in value:
        value = value.split("-", 1)[0]
    if "_" in value:
        value = value.split("_", 1)[0]
    return value


def _tokenize_text(text):
    return re.findall(r"[^\W_]+(?:['’-][^\W_]+)?|\d+", str(text or "").lower(), flags=re.UNICODE)


def _looks_like_sanskrit_recitation(text, detected_language=""):
    normalized_language = _normalize_language_code(detected_language)
    if normalized_language in SANSKRIT_LANG_CODES:
        return True

    tokens = _tokenize_text(text)
    if len(tokens) < 2:
        return False

    marker_hits = sum(1 for token in tokens if token in SANSKRIT_TOKEN_MARKERS)
    if marker_hits >= 2:
        return True

    transliterated_endings = {"ah", "am", "aya", "ena", "anam", "atma", "bhuta"}
    ending_hits = 0
    for token in tokens:
        if len(token) < 4:
            continue
        if any(token.endswith(ending) for ending in transliterated_endings):
            ending_hits += 1
    return ending_hits >= 3


def _looks_like_scripture_opening_intro(text):
    tokens = _tokenize_text(text)
    if len(tokens) < 1:
        return False
    marker_hits = sum(1 for token in tokens if token in SCRIPTURE_OPENING_MARKERS)
    return marker_hits >= 2


def _contains_non_latin_letters(text):
    for char in str(text or ""):
        if not char.isalpha():
            continue
        if ord(char) > 127:
            return True
    return False


def _annotate_opening_language_segments(segments):
    annotated = []
    previous_preserved = False
    for seg in segments:
        enriched = dict(seg)
        start = float(enriched.get("start", 0.0))
        text = enriched.get("text", "")
        detected_language = enriched.get("detected_language", "")
        normalized_language = _normalize_language_code(detected_language)
        normalized_tokens = set(_tokenize_text(text))
        preserve_original_audio = (
            start <= OPENING_PRESERVE_WINDOW_SEC
            and _looks_like_sanskrit_recitation(text, detected_language)
        )
        if not preserve_original_audio and start <= OPENING_PRESERVE_WINDOW_SEC:
            preserve_original_audio = _looks_like_scripture_opening_intro(text)
        if (
            not preserve_original_audio
            and previous_preserved
            and start <= OPENING_PRESERVE_WINDOW_SEC
        ):
            preserve_original_audio = bool(
                normalized_tokens and normalized_tokens.issubset(SCRIPTURE_TRANSLATION_CUES)
            )
        if (
            not preserve_original_audio
            and start <= OPENING_PRESERVE_WINDOW_SEC
            and normalized_language
            and normalized_language not in {"en", "english"}
            and _contains_non_latin_letters(text)
        ):
            preserve_original_audio = True
        enriched["preserve_original_audio"] = preserve_original_audio
        annotated.append(enriched)
        previous_preserved = preserve_original_audio
    return annotated


def _merge_opening_recovery_segments(existing_segments, recovered_segments, total_duration):
    existing = _normalize_segments(existing_segments, total_duration)
    recovered = _normalize_segments(recovered_segments, total_duration)
    recovered = _annotate_opening_language_segments(recovered)
    preserved_recovered = [
        seg for seg in recovered if seg.get("preserve_original_audio")
    ]
    if not preserved_recovered:
        return existing

    replacement_end = max(float(seg["end"]) for seg in preserved_recovered)
    replacement_segments = [
        seg for seg in recovered if float(seg["start"]) < (replacement_end + 0.05)
    ]
    if not replacement_segments:
        return existing

    remaining_segments = [
        seg for seg in existing if float(seg["start"]) >= (replacement_end - 0.05)
    ]
    merged = _normalize_segments(replacement_segments + remaining_segments, total_duration)
    log(
        "TRANSCRIBE",
        f"Opening recovery replaced leading transcript up to {replacement_end:.2f}s with {len(replacement_segments)} recovered segment(s)",
    )
    return merged


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
    "swayambhaga": "Swayambhaga",
    "swayambaha": "Swayambhaga",
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
    "swayambhaga": ["swayambaha", "svayambaha", "svayambhaga", "swayambaga"],
}

# File to store user-approved transcription fixes
TRANSCRIPTION_FIXES_FILE = os.path.join(
    os.path.expanduser("~"), ".video_dubber_transcription_fixes.json"
)
TRANSCRIPTION_PENDING_FIXES_FILE = TRANSCRIPTION_FIXES_FILE.replace(
    ".json", "_pending.json"
)
TRANSCRIPTION_REJECTED_FIXES_FILE = TRANSCRIPTION_FIXES_FILE.replace(
    ".json", "_rejected.json"
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


# Module-level cache for the user-editable fix JSON files.
# Key: path (str). Value: ((mtime_ns, size), parsed_dict).
# A missing file is cached as key=None so we don't re-stat endlessly when
# no fixes have ever been approved. Writes through _save_* bump the
# file's mtime, which naturally invalidates the cache on the next read.
_FIX_FILE_CACHE = {}


def _read_json_dict_cached(path):
    """Read a JSON file into a dict, with mtime/size-keyed memoization.

    Under normal transcription load, _get_all_fixes() is called per-word
    per-chunk, which used to reopen and re-parse the same JSON on every
    invocation (tens to hundreds of times per transcribe). Stat'ing the
    file is ~microseconds; parsing it is tens of ms — so we cache by
    (mtime_ns, size) and only re-read when one changes. External editors
    that rewrite the file bump mtime, so user edits mid-session still
    propagate on the next call.
    """
    try:
        stat = os.stat(path)
        key = (stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError:
        key = None
    except Exception:
        # Unexpected stat failure — treat as missing, don't cache.
        return {}

    cached = _FIX_FILE_CACHE.get(path)
    if cached is not None and cached[0] == key:
        return cached[1]

    if key is None:
        data = {}
    else:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

    _FIX_FILE_CACHE[path] = (key, data)
    return data


def _invalidate_fix_cache(path):
    """Drop a file from the fix cache after a write, so the next read is fresh.

    mtime-based invalidation already handles this on most filesystems, but
    same-second writes on coarse-mtime systems (FAT, some Windows fs)
    could otherwise serve stale data. An explicit drop on write is free
    insurance.
    """
    _FIX_FILE_CACHE.pop(path, None)
    _ALL_FIXES_CACHE["key"] = _ALL_FIXES_CACHE_SENTINEL


def _load_user_fixes():
    """Load user-approved transcription fixes from file."""
    return _read_json_dict_cached(TRANSCRIPTION_FIXES_FILE)


def _save_user_fixes(fixes):
    """Save user-approved transcription fixes to file."""
    try:
        with open(TRANSCRIPTION_FIXES_FILE, "w", encoding="utf-8") as f:
            json.dump(fixes, f, indent=2, ensure_ascii=False)
        _invalidate_fix_cache(TRANSCRIPTION_FIXES_FILE)
    except Exception as e:
        log("TRANSCRIBE", f"Failed to save transcription fixes: {e}")


def _load_rejected_fixes():
    """Load user-rejected transcription fix suggestions."""
    return _read_json_dict_cached(TRANSCRIPTION_REJECTED_FIXES_FILE)


def _save_rejected_fixes(rejections):
    """Save rejected transcription fix suggestions."""
    try:
        with open(TRANSCRIPTION_REJECTED_FIXES_FILE, "w", encoding="utf-8") as f:
            json.dump(rejections, f, indent=2, ensure_ascii=False)
        _invalidate_fix_cache(TRANSCRIPTION_REJECTED_FIXES_FILE)
    except Exception as e:
        log("TRANSCRIBE", f"Failed to save rejected transcription fixes: {e}")


def _load_pending_fixes():
    """Load pending transcription fix suggestions."""
    return _read_json_dict_cached(TRANSCRIPTION_PENDING_FIXES_FILE)


def _save_pending_fixes(pending):
    """Persist pending transcription fix suggestions."""
    try:
        with open(TRANSCRIPTION_PENDING_FIXES_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f, indent=2, ensure_ascii=False)
        _invalidate_fix_cache(TRANSCRIPTION_PENDING_FIXES_FILE)
    except Exception as e:
        log("TRANSCRIBE", f"Failed to save pending transcription fixes: {e}")


# _get_all_fixes() returns TRANSCRIPTION_FIXES merged with user fixes. The
# merge itself is cheap, but it sits inside per-word hot loops during
# transcription. Cache the merged dict keyed on user-fix mtime/size so we
# only rebuild when user fixes change. A sentinel ensures the first call
# always materializes (since "no key" would otherwise collide with a
# missing-file key of None).
_ALL_FIXES_CACHE_SENTINEL = object()
_ALL_FIXES_CACHE = {"key": _ALL_FIXES_CACHE_SENTINEL, "value": None}


def _get_all_fixes():
    """Get combined fixes from built-in and user-approved (memoized)."""
    try:
        stat = os.stat(TRANSCRIPTION_FIXES_FILE)
        key = (stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError:
        key = None
    except Exception:
        key = None

    if _ALL_FIXES_CACHE["key"] is not _ALL_FIXES_CACHE_SENTINEL and _ALL_FIXES_CACHE["key"] == key:
        return _ALL_FIXES_CACHE["value"]

    all_fixes = dict(TRANSCRIPTION_FIXES)
    all_fixes.update(_load_user_fixes())
    _ALL_FIXES_CACHE["key"] = key
    _ALL_FIXES_CACHE["value"] = all_fixes
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

    return _normalize_protected_phrases(" ".join(fixed_words))


def _suggest_fix(original_word, suggested_word):
    """Suggest a transcription fix for user approval."""
    user_fixes = _load_user_fixes()
    rejected_fixes = _load_rejected_fixes()

    # Check if already in built-in or user fixes
    word_lower = original_word.lower()
    if word_lower in TRANSCRIPTION_FIXES or word_lower in user_fixes:
        return False  # Already have a fix for this word

    rejected_for_word = rejected_fixes.get(word_lower, [])
    if suggested_word in rejected_for_word:
        return False

    # Add to pending suggestions
    pending = _load_pending_fixes()

    if word_lower not in pending:
        pending[word_lower] = suggested_word
        try:
            _save_pending_fixes(pending)
            log(
                "TRANSCRIBE", f"  Suggested fix: '{original_word}' → '{suggested_word}'"
            )
            return True
        except Exception:
            pass

    return False


def get_pending_fixes():
    """Get pending transcription fixes for user review."""
    return _load_pending_fixes()


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
        remaining = {k: v for k, v in pending.items() if k not in fixes_to_approve}
        _save_pending_fixes(remaining)
        log("TRANSCRIBE", f"Approved {approved_count} transcription fixes")

    return approved_count


def reject_fixes(fixes_to_reject):
    """Reject pending transcription fixes so they stop reappearing."""
    pending = get_pending_fixes()
    rejected = _load_rejected_fixes()
    rejected_count = 0

    for word, correction in fixes_to_reject.items():
        word_lower = str(word or "").lower()
        correction = str(correction or "").strip()
        if word_lower not in pending:
            continue
        rejected[word_lower] = list(
            dict.fromkeys(list(rejected.get(word_lower, [])) + [correction])
        )
        rejected_count += 1

    if rejected_count > 0:
        remaining = {k: v for k, v in pending.items() if k not in fixes_to_reject}
        _save_rejected_fixes(rejected)
        _save_pending_fixes(remaining)
        log("TRANSCRIBE", f"Rejected {rejected_count} transcription fixes")

    return rejected_count


def clear_pending_fixes():
    """Clear all pending transcription fixes."""
    try:
        if os.path.exists(TRANSCRIPTION_PENDING_FIXES_FILE):
            os.remove(TRANSCRIPTION_PENDING_FIXES_FILE)
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


def _deepgram_chunk_transcribe(api_key, audio_path, language=None):
    """Send a single WAV chunk to Deepgram /v1/listen and return the parsed JSON.

    Deepgram accepts the raw audio bytes as the request body (not multipart),
    with the model + formatting options passed as query parameters. We use
    ``utterances=true`` because it emits speaker/phrase-level spans with
    their own start/end, which maps cleanly onto our segment shape.
    ``smart_format=true`` normalizes punctuation and casing — closer to the
    Whisper ``verbose_json`` output we used to consume from Groq.
    """
    track_api_call("deepgram")
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/wav",
    }

    params = {
        "model": DEEPGRAM_MODEL,
        "smart_format": "true",
        "utterances": "true",
        "punctuate": "true",
    }
    # Language handling: Deepgram wants either a specific BCP-47 code or
    # ``detect_language=true``. If the caller passed "auto" or left it None,
    # flip on detection; otherwise pin the language so we don't regress
    # accuracy on short clips by re-detecting.
    if language and str(language).lower() not in ("auto", "none", ""):
        params["language"] = str(language)
    else:
        params["detect_language"] = "true"

    with open(audio_path, "rb") as f:
        data = f.read()

    r = httpx.post(
        DEEPGRAM_API_URL,
        headers=headers,
        params=params,
        content=data,
        timeout=300,
    )
    if r.is_success:
        track_api_success("deepgram")
    if not r.is_success:
        log("TRANSCRIBE", f"Deepgram error body: {r.text[:300]}")
        r.raise_for_status()
    return r.json()


def _extract_deepgram_language(payload):
    """Pull the detected language code out of a Deepgram response payload.

    Deepgram's language detection surfaces inside
    ``results.channels[0].detected_language``. We also fall back to the
    first alternative's language field for robustness across API versions.
    """
    try:
        channels = (payload.get("results") or {}).get("channels") or []
        if channels:
            ch = channels[0] or {}
            lang = ch.get("detected_language") or ch.get("language")
            if lang:
                return str(lang)
            alternatives = ch.get("alternatives") or []
            if alternatives:
                alt_lang = (alternatives[0] or {}).get("language")
                if alt_lang:
                    return str(alt_lang)
    except Exception:
        pass
    return None


def _deepgram_transcribe(api_key, audio_path, language, output_dir):
    """Transcribe via Deepgram and return ``(segments, detected_language)``.

    Keeps the same return shape as the old ``_groq_transcribe`` so the rest
    of the pipeline (coverage audit, opening-language recovery, fix
    application) stays untouched. Each Deepgram ``utterance`` becomes one
    segment with ``start``, ``end``, ``text``, ``detected_language``.
    """
    chunks = _split_audio(audio_path, output_dir)
    if not chunks:
        raise RuntimeError("Audio chunking produced no chunks for Deepgram transcription.")
    all_segments = []
    time_offset = 0.0
    detected_lang = None

    for chunk_path in chunks:
        log("TRANSCRIBE", f"Deepgram transcribing: {os.path.basename(chunk_path)} ...")
        result = _deepgram_chunk_transcribe(api_key, chunk_path, language)
        chunk_lang = _extract_deepgram_language(result) or language
        if chunk_lang:
            detected_lang = chunk_lang

        utterances = ((result.get("results") or {}).get("utterances")) or []
        if utterances:
            for utt in utterances:
                text = (utt.get("transcript") or "").strip()
                if not text:
                    continue
                start = float(utt.get("start", 0.0))
                end = float(utt.get("end", start))
                fixed_text = _apply_transcription_fixes(text)
                all_segments.append(
                    {
                        "id": len(all_segments),
                        "start": round(start + time_offset, 3),
                        "end": round(end + time_offset, 3),
                        "text": fixed_text,
                        "detected_language": detected_lang,
                    }
                )
        else:
            # Fallback: Deepgram didn't return utterances (can happen on
            # ultra-short probes) — stitch paragraphs or the single
            # alternative transcript into one segment so we don't silently
            # drop speech.
            alternatives = (
                (result.get("results") or {}).get("channels") or [{}]
            )[0].get("alternatives") or []
            alt = alternatives[0] if alternatives else {}
            text = (alt.get("transcript") or "").strip()
            if text:
                words = alt.get("words") or []
                start = float(words[0].get("start", 0.0)) if words else 0.0
                end = float(words[-1].get("end", start)) if words else 0.0
                fixed_text = _apply_transcription_fixes(text)
                all_segments.append(
                    {
                        "id": len(all_segments),
                        "start": round(start + time_offset, 3),
                        "end": round(end + time_offset, 3),
                        "text": fixed_text,
                        "detected_language": detected_lang,
                    }
                )

        # Advance by actual chunk duration so silent chunk tails do not shift
        # later timestamps.
        time_offset += _ffprobe_duration(chunk_path)

    return all_segments, detected_lang


def _local_transcribe(
    audio_path, language, model_size, output_dir, vad_filter=True, beam_size=5
):
    lang_code = language if language and language != "auto" else None

    try:
        from faster_whisper import WhisperModel

        cache_key = (model_size, "cpu", "int8")
        model = _WHISPER_MODEL_CACHE.get(cache_key)
        if model is None:
            log(
                "TRANSCRIBE",
                f"Local Whisper (faster-whisper): {model_size} (loading model)",
            )
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _WHISPER_MODEL_CACHE[cache_key] = model
        else:
            log(
                "TRANSCRIBE",
                f"Local Whisper (faster-whisper): {model_size} (cached)",
            )
        fw_segments, info = model.transcribe(
            audio_path,
            language=lang_code,
            beam_size=beam_size,
            vad_filter=vad_filter,
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
                    "detected_language": detected,
                }
            )
        log(
            "TRANSCRIBE",
            f"Lang: {detected} p={getattr(info, 'language_probability', 0):.2f}",
        )
        return segments, detected
    except Exception as e:
        raise RuntimeError(
            "Local transcription failed. Set DEEPGRAM_API_KEY for cloud transcription "
            "or install faster-whisper (pip install faster-whisper)."
        ) from e


# Raw VAD/ASR segments shorter than this are almost always noise (breath,
# click, silence mislabel) and produce chipmunk-TTS artifacts because the
# dub pipeline must time-compress TTS audio to fit the tiny slot. Dropping
# them preserves dubbing quality at the cost of losing genuine sub-100ms
# spoken content, which is rare in natural speech.
MIN_RAW_SEGMENT_DURATION = 0.10  # seconds


def _normalize_segments(segments, total_duration=None):
    normalized = []
    dropped_short = 0
    for seg in sorted(segments, key=lambda s: (float(s.get("start", 0.0)), float(s.get("end", 0.0)))):
        text = (seg.get("text") or "").strip()
        if not _looks_like_spoken_text(text):
            continue
        start = max(float(seg.get("start", 0.0)), 0.0)
        end = max(float(seg.get("end", start)), start)
        if total_duration is not None:
            start = min(start, total_duration)
            end = min(end, total_duration)
        duration = end - start
        # Subtract a small float-tolerance so nominally-100ms segments aren't
        # dropped due to floating-point representation (e.g., 4.1-4.0 = 0.0999…).
        if duration < MIN_RAW_SEGMENT_DURATION - 1e-6:
            dropped_short += 1
            log(
                "TRANSCRIBE",
                f"  Dropping sub-{int(MIN_RAW_SEGMENT_DURATION * 1000)}ms segment "
                f"({duration * 1000:.0f}ms) text={text[:40]!r}",
            )
            continue
        normalized.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                **{
                    k: v
                    for k, v in seg.items()
                    if k not in {"id", "start", "end", "text"}
                },
            }
        )

    if dropped_short:
        log(
            "TRANSCRIBE",
            f"Dropped {dropped_short} sub-{int(MIN_RAW_SEGMENT_DURATION * 1000)}ms segment(s) "
            "as likely VAD noise",
        )

    for i, seg in enumerate(normalized):
        seg["id"] = i
    return normalized


def _build_uncovered_ranges(segments, total_duration):
    ranges = []
    cursor = 0.0
    for seg in sorted(segments, key=lambda s: s["start"]):
        start = max(0.0, min(float(seg["start"]), total_duration))
        end = max(start, min(float(seg["end"]), total_duration))
        if start > cursor:
            ranges.append((round(cursor, 3), round(start, 3)))
        cursor = max(cursor, end)
    if cursor < total_duration:
        ranges.append((round(cursor, 3), round(total_duration, 3)))
    return ranges


def _should_probe_range(start, end, total_duration):
    gap = end - start
    near_edge = start <= 1.0 or (total_duration - end) <= 1.0
    min_gap = MIN_EDGE_GAP_PROBE_SEC if near_edge else max(MIN_GAP_PROBE_SEC, 1.5)
    return gap >= min_gap


def _extract_audio_range(src_wav, start, end, output_path):
    duration = max(end - start, 0.0)
    if duration <= 0.0:
        return False
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(round(start, 3)),
            "-i",
            src_wav,
            "-t",
            str(round(duration, 3)),
            "-ar",
            PROBE_AUDIO_SAMPLE_RATE,
            "-ac",
            PROBE_AUDIO_CHANNELS,
            output_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return (
        r.returncode == 0
        and os.path.exists(output_path)
        and os.path.getsize(output_path) > MIN_PROBE_AUDIO_BYTES
    )


def _probe_range_for_segments(
    start,
    end,
    wav_path,
    output_dir,
    deepgram_key,
    language,
    model_size,
):
    probe_name = f"probe_{int(start * 1000):010d}_{int(end * 1000):010d}"
    probe_dir = os.path.join(output_dir, "coverage_probes")
    os.makedirs(probe_dir, exist_ok=True)
    probe_audio_path = os.path.join(probe_dir, f"{probe_name}.wav")
    if not _extract_audio_range(wav_path, start, end, probe_audio_path):
        return []

    try:
        if deepgram_key:
            raw_segments, _ = _deepgram_transcribe(
                deepgram_key,
                probe_audio_path,
                None if language in ("auto", None) else language,
                probe_dir,
            )
        else:
            raw_segments, _ = _local_transcribe(
                probe_audio_path,
                language,
                model_size,
                probe_dir,
                vad_filter=True,
                beam_size=5,
            )
            if not raw_segments:
                raw_segments, _ = _local_transcribe(
                probe_audio_path,
                language,
                model_size,
                probe_dir,
                vad_filter=False,
                beam_size=8,
                )
    except Exception as e:
        log(
            "TRANSCRIBE",
            f"Coverage probe failed for {start:.2f}s-{end:.2f}s: {e}",
        )
        return []

    discovered = []
    for seg in raw_segments:
        text = (seg.get("text") or "").strip()
        seg_rel_start = float(seg.get("start", 0.0))
        seg_rel_end = float(seg.get("end", seg_rel_start))
        seg_duration = max(seg_rel_end - seg_rel_start, 0.0)
        if not _looks_like_probe_speech(text, seg_duration):
            continue
        seg_start = start + seg_rel_start
        seg_end = start + seg_rel_end
        seg_end = min(seg_end, end)
        if seg_end <= seg_start:
            seg_end = min(end, seg_start + 0.05)
        discovered.append(
            {
                "start": round(seg_start, 3),
                "end": round(seg_end, 3),
                "text": text,
                "is_gap_probe": True,
                "probe_range_start": round(start, 3),
                "probe_range_end": round(end, 3),
            }
        )

    if discovered:
        log(
            "TRANSCRIBE",
            f"Coverage probe found {len(discovered)} segment(s) in {start:.2f}s-{end:.2f}s",
        )
    else:
        log(
            "TRANSCRIBE",
            f"Coverage probe found no speech in {start:.2f}s-{end:.2f}s",
        )
    return discovered


def _audit_speech_coverage(
    segments,
    total_duration,
    wav_path,
    output_dir,
    deepgram_key,
    language,
    model_size,
):
    normalized = _normalize_segments(segments, total_duration)
    gap_segments = []
    for start, end in _build_uncovered_ranges(normalized, total_duration):
        if not _should_probe_range(start, end, total_duration):
            continue
        gap_segments.extend(
            _probe_range_for_segments(
                start,
                end,
                wav_path,
                output_dir,
                deepgram_key,
                language,
                model_size,
            )
        )

    if gap_segments:
        log(
            "TRANSCRIBE",
            f"Coverage audit recovered {len(gap_segments)} additional speech segment(s)",
        )
    return _normalize_segments(normalized + gap_segments, total_duration)


def _recover_opening_mixed_language(
    segments,
    total_duration,
    wav_path,
    output_dir,
    deepgram_key,
    language,
    model_size,
    detected_language="",
):
    normalized_language = _normalize_language_code(language)
    # When the user chose "auto", fall back to whatever the bulk transcribe
    # pass detected so we still re-probe the opening. Without this, short
    # opening recitations in a different language (e.g., a Sanskrit invocation
    # before the main English talk) never get a second look and stay
    # mis-attached to the surrounding English segment.
    if not normalized_language or normalized_language == "auto":
        normalized_language = _normalize_language_code(detected_language)
    if not normalized_language or normalized_language == "auto":
        return _annotate_opening_language_segments(
            _normalize_segments(segments, total_duration)
        )

    probe_end = min(total_duration, OPENING_RECOVERY_WINDOW_SEC)
    if probe_end <= 0.5:
        return _annotate_opening_language_segments(
            _normalize_segments(segments, total_duration)
        )

    # The re-probe itself is still language-free (None): we want Whisper to
    # re-detect on the isolated opening slice. The bulk language above is
    # only the gate that lets us reach this call path under auto-detect.
    recovered = _probe_range_for_segments(
        0.0,
        probe_end,
        wav_path,
        output_dir,
        deepgram_key,
        None,
        model_size,
    )
    if not recovered:
        return _annotate_opening_language_segments(
            _normalize_segments(segments, total_duration)
        )

    merged = _merge_opening_recovery_segments(segments, recovered, total_duration)
    return _annotate_opening_language_segments(merged)


def transcribe_audio(
    video_path,
    output_dir,
    model_size="large",
    language="auto",
    deepgram_api_key=None,
    prefer_local=False,
):
    os.makedirs(output_dir, exist_ok=True)
    wav_path = os.path.join(output_dir, "audio.wav")
    _extract_audio(video_path, wav_path)

    deepgram_key = get_deepgram_api_key(deepgram_api_key)

    # prefer_local is used by the dub verifier: Deepgram nova-3 is
    # English-primary and cannot properly read Indic scripts
    # (Gujarati/Hindi/etc.), so verifying a Hindi/Gujarati dub against the
    # translated transcript needs local Whisper to read Devanagari / Gujarati
    # correctly. Source-audio transcription (usually English) keeps using
    # Deepgram where it shines.
    if deepgram_key and not prefer_local:
        log("TRANSCRIBE", f"Using Deepgram {DEEPGRAM_MODEL} (lang={language}) ...")
        try:
            lang_code = None if language in ("auto", None) else language
            segments, detected = _deepgram_transcribe(
                deepgram_key, wav_path, lang_code, output_dir
            )
            log("TRANSCRIBE", f"Lang detected: {detected}")
        except Exception as e:
            log("TRANSCRIBE", f"Deepgram failed: {e} — falling back to local Whisper ...")
            segments, detected = _local_transcribe(
                wav_path, language, model_size, output_dir
            )
    else:
        if prefer_local:
            log(
                "TRANSCRIBE",
                f"prefer_local=True (verifier) — using local Whisper (lang={language}) ...",
            )
        else:
            log("TRANSCRIBE", "No DEEPGRAM_API_KEY — using local Whisper ...")
        segments, detected = _local_transcribe(
            wav_path, language, model_size, output_dir
        )

    total_duration = _ffprobe_duration(video_path)
    if prefer_local:
        # When prefer_local is set, the caller (dub verifier) trusts local
        # Whisper's output as-is. The audit and opening-recovery helpers
        # were built to catch gaps in Deepgram's segmentation and run
        # per-gap probes through Deepgram — on Indic audio those probes
        # return plausible-looking English garbage that corrupts the
        # segment list and wastes API calls. Whisper's built-in VAD and
        # timestamp logic is already good enough for coverage comparison,
        # so skip both helpers here.
        segments = _normalize_segments(segments, total_duration)
    else:
        segments = _audit_speech_coverage(
            segments,
            total_duration,
            wav_path,
            output_dir,
            deepgram_key,
            language,
            model_size,
        )
        segments = _recover_opening_mixed_language(
            segments,
            total_duration,
            wav_path,
            output_dir,
            deepgram_key,
            language,
            model_size,
            detected_language=detected,
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
