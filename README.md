# Video Dubber v2.0

## Pipeline
1. Download (YouTube URL or local file)
2. BGM separation (demucs — vocals stripped, music kept)
3. Transcribe (faster-whisper)
4. Translate (deep-translator)
5. TTS (edge-tts, natural speed — video slows to match)
6. Build dubbed video (ffmpeg)
7. Teaser clip cut from dubbed video
8. Vision extraction (GPT-4o → main_topic, core_conflict, provocative_angle, theme)
9. Per-platform caption generation (GPT-4o, your CAPTION_PROMPT)
10. **Review UI** — edit any caption before publishing
11. Publish to all platforms via Zernio API

## Install
```
pip install -r requirements.txt
```

## API Keys needed
- OpenAI (GPT-4o for vision + captions)
- Zernio (publishing)
Both saved to .env via the UI.

## Run
```
python app.py
```
