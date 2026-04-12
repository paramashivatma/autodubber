import os, subprocess, json
from .utils import log

def is_url(s):
    return s.startswith("http://") or s.startswith("https://")

def _fetch_source_metadata(url):
    r = subprocess.run(
        ["yt-dlp", "--dump-single-json", "--no-playlist", "--no-warnings", url],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp metadata fetch failed:\n{r.stderr[-600:]}")
    raw = json.loads(r.stdout or "{}")
    return {
        "title": raw.get("title") or "",
        "description": raw.get("description") or "",
        "tags": raw.get("tags") or [],
        "webpage_url": raw.get("webpage_url") or url,
        "uploader": raw.get("uploader") or "",
        "extractor": raw.get("extractor_key") or raw.get("extractor") or "",
        "is_live": bool(raw.get("is_live")),
        "was_live": bool(raw.get("was_live")),
        "availability": raw.get("availability") or "",
        "source_url": url,
    }


def download_video(url, output_dir="workspace"):
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "source.mp4")
    metadata_path = os.path.join(output_dir, "source_metadata.json")
    log("DOWNLOAD", f"Fetching {url}")
    source_metadata = {}
    try:
        source_metadata = _fetch_source_metadata(url)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(source_metadata, f, ensure_ascii=False, indent=2)
        log(
            "DOWNLOAD",
            f"Metadata -> extractor={source_metadata.get('extractor', '?')} title={source_metadata.get('title', '')[:80]}",
        )
    except Exception as e:
        log("DOWNLOAD", f"Metadata fetch failed, continuing with media download: {e}")

    r = subprocess.run([
        "yt-dlp","-f","bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format","mp4","-o",out_path,"--no-playlist",url
    ], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{r.stderr[-600:]}")
    log("DOWNLOAD", f"Saved -> {out_path}")
    return {
        "video_path": out_path,
        "source_metadata": source_metadata,
    }
