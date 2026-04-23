import json
import math
import os
import re
import subprocess
from difflib import SequenceMatcher

from .transcriber import transcribe_audio
from .utils import ffprobe_duration as _ffprobe_duration, log

REPORT_FILENAME = "dub_validation_report.json"
VERIFY_CHUNK_SEC = 20.0


def _normalize_text(text):
    text = str(text or "").lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()
    return text


def _tokenize(text):
    normalized = _normalize_text(text)
    raw_tokens = normalized.split()
    tokens = []
    for token in raw_tokens:
        cleaned = token.strip(".,!?;:()[]{}\"'`|/\\-–—")
        cleaned = cleaned.strip()
        if cleaned:
            tokens.append(cleaned)
    return tokens


def _is_significant_token(token):
    if not token:
        return False
    if token.isdigit():
        return True
    alpha_num = sum(ch.isalnum() for ch in token)
    alpha_chars = sum(ch.isalpha() for ch in token)
    return alpha_num >= 3 or alpha_chars >= 2


def _tokens_similar(expected, observed):
    if expected == observed:
        return True
    if len(expected) >= 5 and (expected in observed or observed in expected):
        shorter = min(len(expected), len(observed))
        longer = max(len(expected), len(observed))
        if shorter / longer >= 0.75:
            return True
    return SequenceMatcher(None, expected, observed).ratio() >= 0.84


def _build_expected_text(segments):
    parts = []
    for seg in segments or []:
        text = (seg.get("translated") or seg.get("text") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def _extract_video_chunk(src_path, start_sec, duration_sec, dst_path):
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(round(start_sec, 3)),
            "-i",
            src_path,
            "-t",
            str(round(duration_sec, 3)),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            dst_path,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0 or not os.path.exists(dst_path):
        raise RuntimeError(f"ffmpeg chunk extraction failed for {dst_path}: {r.stderr}")


# Whisper-medium transcribes English / Spanish well enough for
# verification, but on Indic scripts (Gujarati, Hindi, Tamil, Telugu,
# Kannada, Malayalam, Bengali) and other low-resource targets its output
# diverges badly from large — observed in prod as Coverage 0% with a 97%
# observed-char ratio on Gujarati (right-length output, wrong content).
# Only downgrade for the Latin-script languages where the optimization
# holds; keep large for anything else the caller requested.
_VERIFIER_DOWNGRADE_LANGUAGES = {"en", "english", "es", "spanish"}


def _verifier_model_size(model_size, target_language):
    """Pick the verifier model size for the given target language.

    Conditionally downgrades large → medium to save ~50% inference time
    plus the ~1m 46s first-chunk large-model load. Only runs for English
    and Spanish; Indic / Cyrillic / other non-Latin targets stay on large
    because medium's accuracy on those languages is not fit for purpose
    (see block comment on ``_VERIFIER_DOWNGRADE_LANGUAGES``).
    """
    if str(model_size or "").lower() != "large":
        return model_size
    lang = str(target_language or "").lower()
    if lang in _VERIFIER_DOWNGRADE_LANGUAGES:
        return "medium"
    return model_size


def _retranscribe_video_in_chunks(video_path, verify_dir, target_language, model_size):
    duration = _ffprobe_duration(video_path)
    chunk_dir = os.path.join(verify_dir, "chunks")
    os.makedirs(chunk_dir, exist_ok=True)

    verifier_size = _verifier_model_size(model_size, target_language)

    observed_segments = []
    chunk_index = 0
    start_sec = 0.0

    while start_sec < duration - 0.05:
        chunk_duration = min(VERIFY_CHUNK_SEC, duration - start_sec)
        chunk_video = os.path.join(chunk_dir, f"chunk_{chunk_index:03d}.mp4")
        chunk_output_dir = os.path.join(chunk_dir, f"chunk_{chunk_index:03d}")
        os.makedirs(chunk_output_dir, exist_ok=True)

        _extract_video_chunk(video_path, start_sec, chunk_duration, chunk_video)
        # prefer_local=True: Deepgram nova-3 is English-primary and cannot
        # read Indic scripts (Gujarati/Hindi/etc.) reliably. Without this,
        # the verifier hallucinates right-length-but-wrong-script
        # transcripts and flags every Indic dub as failing coverage. Local
        # Whisper-large handles these scripts correctly.
        chunk_segments = transcribe_audio(
            chunk_video,
            chunk_output_dir,
            model_size=verifier_size,
            language=target_language,
            prefer_local=True,
        )

        for seg in chunk_segments:
            observed_segments.append(
                {
                    **seg,
                    "start": round(float(seg.get("start", 0.0)) + start_sec, 3),
                    "end": round(float(seg.get("end", 0.0)) + start_sec, 3),
                }
            )

        start_sec += chunk_duration
        chunk_index += 1

    return observed_segments


def _compare_token_coverage(expected_text, observed_text):
    expected_tokens = [tok for tok in _tokenize(expected_text) if _is_significant_token(tok)]
    observed_tokens = [tok for tok in _tokenize(observed_text) if _is_significant_token(tok)]

    matched = 0
    missing = []
    cursor = 0

    for token in expected_tokens:
        found_at = None
        for idx in range(cursor, len(observed_tokens)):
            if _tokens_similar(token, observed_tokens[idx]):
                found_at = idx
                break
        if found_at is None:
            missing.append(token)
            continue
        matched += 1
        cursor = found_at + 1

    unique_missing = []
    seen = set()
    for token in missing:
        if token in seen:
            continue
        seen.add(token)
        unique_missing.append(token)

    total = len(expected_tokens)
    coverage = (matched / total) if total else 1.0
    return {
        "expected_significant_tokens": total,
        "observed_significant_tokens": len(observed_tokens),
        "matched_significant_tokens": matched,
        "coverage_ratio": round(coverage, 4),
        "missing_tokens": unique_missing,
    }


def _max_repeated_token_run(tokens):
    longest = 0
    current = 0
    prev = None
    for token in tokens:
        if token == prev:
            current += 1
        else:
            current = 1
            prev = token
        if current > longest:
            longest = current
    return longest


def _assess_transcript_quality(observed_text):
    tokens = [tok for tok in _tokenize(observed_text) if _is_significant_token(tok)]
    token_count = len(tokens)
    unique_ratio = (len(set(tokens)) / token_count) if token_count else 0.0
    replacement_char_count = observed_text.count("\ufffd")
    repeated_run = _max_repeated_token_run(tokens)
    looks_unreliable = (
        replacement_char_count > 0
        or repeated_run >= 4
        or (token_count >= 20 and unique_ratio < 0.35)
    )
    return {
        "replacement_char_count": replacement_char_count,
        "max_repeated_token_run": repeated_run,
        "observed_unique_token_ratio": round(unique_ratio, 4),
        "looks_unreliable": looks_unreliable,
    }


def verify_dubbed_output(
    video_path,
    segments,
    target_language,
    output_dir,
    model_size="large",
):
    # Callers pass whatever size the main pipeline is using (typically
    # "large"). _retranscribe_video_in_chunks auto-downgrades large →
    # medium for English / Spanish; keeps large for Indic, Cyrillic, and
    # other non-Latin targets where medium is not accurate enough. See
    # _verifier_model_size() for the full rationale.
    verify_dir = os.path.join(output_dir, "dub_verification")
    os.makedirs(verify_dir, exist_ok=True)

    expected_text = _build_expected_text(segments)
    if not expected_text:
        raise RuntimeError("Dub verification could not build an expected translated script.")

    log("VERIFY", f"Retranscribing dubbed output for QA: {os.path.basename(video_path)}")
    observed_segments = _retranscribe_video_in_chunks(
        video_path,
        verify_dir,
        target_language,
        model_size,
    )
    with open(os.path.join(verify_dir, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump(observed_segments, f, ensure_ascii=False, indent=2)
    observed_text = " ".join((seg.get("text") or "").strip() for seg in observed_segments).strip()

    token_report = _compare_token_coverage(expected_text, observed_text)
    quality_report = _assess_transcript_quality(observed_text)
    text_similarity = round(
        SequenceMatcher(None, _normalize_text(expected_text), _normalize_text(observed_text)).ratio(),
        4,
    )
    missing_count = len(token_report["missing_tokens"])
    expected_count = token_report["expected_significant_tokens"]
    observed_count = token_report["observed_significant_tokens"]
    coverage_ratio = token_report["coverage_ratio"]
    observed_ratio = round((observed_count / expected_count), 4) if expected_count else 1.0
    expected_chars = len(_normalize_text(expected_text))
    observed_chars = len(_normalize_text(observed_text))
    observed_char_ratio = round((observed_chars / expected_chars), 4) if expected_chars else 1.0

    allowed_missing = max(2, math.ceil(expected_count * 0.08)) if expected_count else 0
    transcript_truncated = observed_ratio < 0.55 or observed_char_ratio < 0.55
    quality_reliable = not quality_report["looks_unreliable"]
    passed = (
        coverage_ratio >= 0.82
        and missing_count <= allowed_missing
        and not transcript_truncated
    )
    blocking_failure = (not passed) and quality_reliable

    report = {
        "passed": passed,
        "blocking_failure": blocking_failure,
        "target_language": target_language,
        "video_path": os.path.abspath(video_path),
        "expected_text": expected_text,
        "observed_text": observed_text,
        "text_similarity": text_similarity,
        "allowed_missing_tokens": allowed_missing,
        "observed_token_ratio": observed_ratio,
        "observed_char_ratio": observed_char_ratio,
        "transcript_truncated": transcript_truncated,
        "quality_reliable": quality_reliable,
        **token_report,
        **quality_report,
    }

    report_path = os.path.join(output_dir, REPORT_FILENAME)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if passed:
        log(
            "VERIFY",
            f"Dub verification passed: coverage={coverage_ratio:.2%}, observed={observed_ratio:.2%}",
        )
        return report

    if not blocking_failure:
        log(
            "VERIFY",
            "Dub verification inconclusive: retranscribed QA audio was too noisy to trust as a blocking failure. "
            f"coverage={coverage_ratio:.2%}, observed={observed_ratio:.2%}",
        )
        return report

    missing_preview = ", ".join(report["missing_tokens"][:8]) or "unknown terms"
    log(
        "VERIFY",
        f"Dub verification failed: coverage={coverage_ratio:.2%}, observed={observed_ratio:.2%}, missing={missing_preview}",
    )
    raise RuntimeError(
        "Dub verification failed before caption generation. "
        f"Coverage {coverage_ratio:.0%}; observed transcript ratio {observed_ratio:.0%}; "
        f"likely missing terms: {missing_preview}. "
        f"See {report_path}."
    )
