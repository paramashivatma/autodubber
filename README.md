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
- `GEMINI_API_KEY` (translation, vision, flyer OCR/captioning)
- `MISTRAL_API_KEY` (caption generation)
- `ZERNIO_API_KEY` (publishing)
- `GROQ_API_KEY` (optional, faster transcription)

Optional for Google Sheet logging:
- `GOOGLE_SHEET_ID`
- `GOOGLE_CREDENTIALS_FILE` (defaults to `credentials.json`)

Config is read from `.env` (see `.env.example`).

## Run
```
python app.py
```
