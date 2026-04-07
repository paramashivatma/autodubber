import os, subprocess, shutil
from pydub import AudioSegment
from .utils import log


def _ffprobe_duration(path):
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError(f"ffprobe failed for: {path}\n{r.stderr}")


def _cut(src, start, end, dst):
    dur = max(round(end - start, 4), 0.1)
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(round(start, 4)),
            "-i",
            src,
            "-t",
            str(dur),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-an",
            dst,
        ],
        capture_output=True,
        timeout=300,
    )
    if r.returncode != 0 or not os.path.exists(dst):
        log("CUT", f"  FFmpeg cut failed for {os.path.basename(dst)}, copying source")
        shutil.copy(src, dst)


def _slow(src, dst, pts_factor):
    pts = min(round(pts_factor, 5), 4.0)
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-filter:v",
            f"setpts={pts}*PTS",
            "-an",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "22",
            dst,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        log(
            "SLOW", f"  FFmpeg failed, copying source as fallback (A/V sync may differ)"
        )
        shutil.copy(src, dst)
        return False
    return True


def _actual_duration(path):
    try:
        return _ffprobe_duration(path)
    except Exception:
        return None


def _pad_audio_with_silence(audio_path, target_dur_ms):
    """Pad audio with silence to reach target duration (in milliseconds)."""
    if not audio_path or not os.path.exists(audio_path):
        return None
    try:
        audio = AudioSegment.from_file(audio_path)
        current_ms = len(audio)
        if target_dur_ms <= current_ms:
            return None
        silence_ms = target_dur_ms - current_ms
        if silence_ms < 50:
            return None
        silence = AudioSegment.silent(duration=silence_ms)
        padded = audio + silence
        padded_path = audio_path.replace(".wav", f"_padded.wav")
        padded.export(padded_path, format="wav")
        return padded_path
    except Exception as e:
        log("BUILD", f"    -> failed to pad audio: {e}")
        return None


def _concat(parts, dst):
    list_file = dst + "_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in parts:
            safe = os.path.abspath(p).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe}'\n")
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-an",
            dst,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    try:
        os.remove(list_file)
    except:
        pass
    if r.returncode != 0:
        log("BUILD", f"Concat error:\n{r.stderr[-500:]}")
        return False
    return True


def build_dubbed_video(
    video_path,
    segments,
    output_path,
    bgm_path=None,
    bgm_volume=0.35,
    output_dir="workspace",
):
    os.makedirs(output_dir, exist_ok=True)
    tmp = os.path.join(output_dir, "_tmp")
    try:
        shutil.rmtree(tmp)
    except Exception:
        pass
    os.makedirs(tmp, exist_ok=True)

    orig_total = _ffprobe_duration(video_path)
    segs = sorted(segments, key=lambda s: s["start"])
    parts = []
    positions = []
    prev = 0.0
    cursor = 0.0

    for i, seg in enumerate(segs):
        seg_start = seg["start"]
        seg_end = min(seg["end"], orig_total)
        orig_dur = max(seg_end - seg_start, 0.1)
        tts_dur = seg.get("audio_dur_ms", orig_dur * 1000) / 1000.0
        gap = seg_start - prev

        if gap > 0.05:
            gf = os.path.join(tmp, f"gap_{i:04d}.mp4")
            _cut(video_path, prev, seg_start, gf)
            if os.path.exists(gf) and os.path.getsize(gf) > 500:
                actual_gap = _actual_duration(gf) or gap
                parts.append(gf)
                cursor += actual_gap

        seg_raw = os.path.join(tmp, f"seg_{i:04d}_raw.mp4")
        seg_out = os.path.join(tmp, f"seg_{i:04d}.mp4")
        _cut(video_path, seg_start, seg_end, seg_raw)

        log(
            "BUILD",
            f"  seg#{seg['id']}: orig={orig_dur:.2f}s tts={tts_dur:.2f}s gap={gap:.2f}s",
        )

        # Always match video to TTS duration (with 1.5x cap)
        target_dur = min(tts_dur, orig_dur * 1.5)  # Cap at 1.5x
        stretch = target_dur / orig_dur

        if stretch > 1.05:  # Stretch video (TTS > Original)
            log("BUILD", f"    → stretch {stretch:.3f}x (capped at 1.5x)")
            stretched = _slow(seg_raw, seg_out, stretch)
            if not stretched:
                log("BUILD", f"    → WARNING: stretch failed, A/V may be out of sync")
            actual_seg_dur = _actual_duration(seg_out) or target_dur
        elif stretch < 0.95:  # Speed up video (TTS < Original)
            log("BUILD", f"    → speed up {stretch:.3f}x")
            # Use ffmpeg to speed up video
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    seg_raw,
                    "-filter:v",
                    f"setpts={stretch}*PTS",
                    "-an",
                    "-r",
                    "30",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "22",
                    seg_out,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if r.returncode != 0:
                log("BUILD", f"    → WARNING: speed up failed, using original")
                shutil.copy(seg_raw, seg_out)
                actual_seg_dur = orig_dur
            else:
                actual_seg_dur = _actual_duration(seg_out) or target_dur
        else:  # No significant difference
            shutil.copy(seg_raw, seg_out)
            actual_seg_dur = _actual_duration(seg_out) or orig_dur

        audio_start = cursor
        parts.append(seg_out)
        cursor += actual_seg_dur
        prev = seg_end

        audio_path = seg.get("audio_path")
        if audio_path and os.path.exists(audio_path):
            # Video now matches TTS duration, so no padding needed
            overlay_dur = tts_dur
            positions.append((audio_start, overlay_dur, audio_path))
            log("BUILD", f"    → audio overlay at {audio_start:.2f}s")
        else:
            log("BUILD", f"    → WARNING: No audio path for seg#{seg['id']}")

    # Only include tail segment if it won't exceed audio duration
    # Video duration should match audio duration to prevent chopped ending
    if prev < orig_total - 0.05:
        tf = os.path.join(tmp, "tail.mp4")
        _cut(video_path, prev, orig_total, tf)
        if os.path.exists(tf) and os.path.getsize(tf) > 500:
            actual_tail = _actual_duration(tf) or (orig_total - prev)
            # Calculate total audio duration
            total_audio_dur = max([pos[0] + pos[1] for pos in positions], default=0)
            # Only add tail if it won't exceed audio duration
            if cursor + actual_tail <= total_audio_dur + 0.5:  # 0.5s tolerance
                parts.append(tf)
                cursor += actual_tail
                log("BUILD", f"  → tail segment added: {actual_tail:.2f}s")
            else:
                log("BUILD", f"  → tail segment skipped (would exceed audio duration)")

    if not parts:
        raise RuntimeError("No video parts to concatenate.")

    joined = os.path.join(output_dir, "_joined.mp4")
    log("BUILD", f"Concatenating {len(parts)} parts ...")
    if not _concat(parts, joined):
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("Concat failed.")

    total_ms = int(cursor * 1000) + 500
    tts_track = AudioSegment.silent(duration=total_ms)
    for audio_start, overlay_dur, cp in positions:
        try:
            tts_audio = AudioSegment.from_file(cp)
            declared_ms = int(overlay_dur * 1000)
            if len(tts_audio) > declared_ms + 100:
                tts_audio = tts_audio[:declared_ms]
            tts_track = tts_track.overlay(tts_audio, position=int(audio_start * 1000))
        except Exception as e:
            log("BUILD", f"  Audio overlay error: {e}")

    if bgm_path and os.path.exists(bgm_path) and bgm_volume > 0.01:
        bgm = AudioSegment.from_file(bgm_path)
        if len(bgm) <= 0:
            log("BUILD", "  BGM track is empty/corrupt — skipping BGM mix")
            mixed = tts_track
        else:
            if len(bgm) < total_ms:
                bgm = bgm * ((total_ms // len(bgm)) + 2)
            bgm = bgm[:total_ms] - int(20 * (1.0 - bgm_volume))
            mixed = bgm.overlay(tts_track)
    else:
        mixed = tts_track

    wav_out = os.path.join(output_dir, "dubbed_audio.wav")
    mixed.export(wav_out, format="wav")

    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            joined,
            "-i",
            wav_out,
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-shortest",
            output_path,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Audio attach failed:\n{r.stderr[-400:]}")

    shutil.rmtree(tmp, ignore_errors=True)
    try:
        os.remove(joined)
    except:
        pass
    log("BUILD", f"Done -> {output_path}")
    return output_path
