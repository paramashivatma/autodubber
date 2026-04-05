import os, json, subprocess
import httpx
from .config import get_groq_api_key
from .utils import log

GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3"
MAX_FILE_MB = 25  # Groq limit


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
            all_segments.append(
                {
                    "id": seg.get("id", len(all_segments)),
                    "start": round(seg["start"] + time_offset, 3),
                    "end": round(seg["end"] + time_offset, 3),
                    "text": seg["text"].strip(),
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
            segments.append(
                {
                    "id": i,
                    "start": round(float(seg.start), 3),
                    "end": round(float(seg.end), 3),
                    "text": text,
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
