# AutoDub Studio (Video Dubber v1.0)
Desktop GUI tool to:
- Dub videos into Indian languages with voice synthesis.
- Generate platform-aware captions/teasers.
- Publish to multiple social platforms via Zernio.
- Process flyer/image posts with OCR + caption generation.

## Why this project
AutoDub Studio is designed for operators who need a repeatable content pipeline from raw source media to publish-ready posts, with review in the middle and strong fallbacks when APIs fail or quotas are hit.

## Key features
- End-to-end video pipeline (URL/local input -> dubbed output -> teaser -> publish).
- Flyer/Image pipeline with multi-image support.
- Caption review step before publishing.
- Platform character limit enforcement (X/Bluesky/Threads/TikTok, etc.).
- Economy/Quality mode for API cost vs quality tradeoff.
- Google Sheet tracking after publish.
- Publish safeguards to prevent duplicate posts from double-clicks.

## Supported publishing platforms
- Video: Instagram, Facebook, YouTube, Threads, X/Twitter, TikTok, Bluesky
- Flyer/Image: Instagram, Facebook, Threads, X/Twitter, Bluesky

Note: Flyer/Image tab intentionally excludes YouTube and TikTok image publishing.

## End-to-end workflow
### Video workflow
1. Source input (YouTube URL or local video file)
2. Optional BGM separation (Demucs)
3. Transcription (Groq if key present; local Whisper fallback)
4. Translation (Gemini-first in quality mode, Google-first in economy mode)
5. TTS generation (Edge TTS)
6. Dubbed video build (FFmpeg stitching + audio mix)
7. Content intelligence extraction
8. Caption generation per platform
9. Teaser generation per platform
10. Caption review/edit in UI
11. Publish through Zernio + optional sheet update

### Flyer/Image workflow
1. Select one or more images
2. OCR text extraction
3. Gujarati caption generation
4. Optional teaser text generation
5. Publish button becomes enabled only after successful processing
6. Publish to selected image-compatible platforms

## Requirements
### System tools
- Python 3.11+
- FFmpeg + FFprobe available in PATH
- Optional: Tesseract OCR (improves OCR quality in Flyer/Image flow)

### Python dependencies
Install from `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Getting started
### 1) Clone + virtual environment
```bash
git clone https://github.com/paramashivatma/autodubber.git
cd autodubber
python -m venv .venv
```

Windows PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
source .venv/bin/activate
```

### 2) Install dependencies
```bash
pip install -r requirements.txt
```

### 3) Configure environment
Copy template and fill values:

```bash
cp .env.example .env
```

On Windows PowerShell:
```powershell
Copy-Item .env.example .env
```

Edit `.env`:

| Variable | Required | Used for |
|---|---|---|
| `ZERNIO_API_KEY` | Yes (for publishing) | Publish to social platforms |
| `GEMINI_API_KEY` | Recommended | Translation, vision extraction, flyer AI steps |
| `MISTRAL_API_KEY` | Recommended | Caption generation |
| `GROQ_API_KEY` | Optional | Fast cloud transcription |
| `GOOGLE_SHEET_ID` | Optional | Sheet logging |
| `GOOGLE_CREDENTIALS_FILE` | Optional | Service account JSON path for Sheets |
| `PIPELINE_MODE` (`economy`/`quality`) | Optional | Cost/performance behavior |

Legacy aliases still supported:
- `GOOGLE_API_KEY`, `GEMINI_VISION_KEY`, `OPENROUTER_API_KEY`, `SHEET_ID`

### 4) Configure platform account IDs (important)
Publishing uses `PLATFORM_ACCOUNTS` in:
- `dubber/utils.py`

Set these IDs to your own Zernio-connected account IDs. If IDs are wrong, publishing will fail with "No valid platform accounts configured" or per-platform account errors.

### 5) Run the app
```bash
python app.py
```

## Daily operator usage
### Dub Video tab
1. Paste URL or browse local video.
2. Choose voice/model/languages.
3. Select publish platforms.
4. Click `Run Dub Pipeline`.
5. Review captions in dialog.
6. Approve and publish.

### Flyer / Image tab
1. Select image(s).
2. Click `Process Flyer`.
3. Review generated logs/captions.
4. Click `Publish Content`.

Tip: Publish is intentionally disabled until flyer processing succeeds.

## Output and working files
- Final dubbed video: `output.mp4` (project root)
- Pipeline working artifacts: `workspace/`
  - transcript/caption/vision files
  - teaser files
  - temporary audio/video intermediates

Use the `Clean Workspace` button to clear temporary artifacts.

## Error handling behavior
- One platform failure does not stop others.
- Unconfirmed/timeout responses are surfaced separately in UI.
- Caption lengths are clamped to platform limits before publish.
- Quota exhaustion triggers fallback routing where available.

## Troubleshooting
### `ffmpeg` / `ffprobe` not found
Install FFmpeg and add it to PATH.

### `yt-dlp failed`
Usually URL/network/content restrictions. Try local file input to verify the rest of the pipeline.

### Gemini 429 / quota exhausted
Switch to `PIPELINE_MODE=economy` and/or use backup translation paths. Logs will show fallback usage.

### Publish reports failure but posts appeared
Treat as unconfirmed response from platform/backend. Check dashboards first before retrying to avoid duplicates.

### Google Sheet update fails
- Verify `GOOGLE_SHEET_ID`
- Verify service account JSON path (`GOOGLE_CREDENTIALS_FILE`)
- Ensure sheet is shared with service account email

### Local transcription fallback fails
Set `GROQ_API_KEY` (recommended), or ensure local Whisper dependencies are properly installed.

## Project structure
```text
app.py
review_dialog.py
dubber/
  transcriber.py
  translator.py
  tts_generator.py
  video_builder.py
  teaser_generator.py
  vision_extractor.py
  caption_generator.py
  image_processor.py
  sdk_publisher.py
  sheet_logger.py
  runtime_config.py
  config.py
  utils.py
```

## Security notes
- Never commit `.env`, credentials JSON, or API keys.
- Rotate keys immediately if exposed.
- Keep this repo private until all keys are confirmed rotated.

## License
This project is licensed under the MIT License. See [LICENSE](LICENSE).
