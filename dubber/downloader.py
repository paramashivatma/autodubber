import os, subprocess
from .utils import log

def is_url(s):
    return s.startswith("http://") or s.startswith("https://")

def download_video(url, output_dir="workspace"):
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "source.mp4")
    log("DOWNLOAD", f"Fetching {url}")
    r = subprocess.run([
        "yt-dlp","-f","bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format","mp4","-o",out_path,"--no-playlist",url
    ], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{r.stderr[-600:]}")
    log("DOWNLOAD", f"Saved -> {out_path}")
    return out_path
