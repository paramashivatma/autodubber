# API Usage Analysis - KAILASA Dubber Pipeline

## Overview of All External APIs

### 1. **TRANSCRIPTION** - Groq API
**File:** `dubber/transcriber.py`
- **Endpoint:** `https://api.groq.com/openai/v1/audio/transcriptions`
- **Model:** `whisper-large-v3`
- **Purpose:** Convert audio to text segments with timestamps
- **API Key:** `GROQ_API_KEY` (env var)
- **Fallback:** Local OpenAI Whisper (if Groq fails or no key)
- **Output:** `transcript.json` with segments (id, start, end, text)

---

### 2. **TRANSLATION** - Multiple APIs
**File:** `dubber/translator.py`

#### Primary: Google Gemini
- **Models:** 
  - `gemini-pro` (single text translation)
  - `gemini-1.5-flash` (batch translation)
- **Purpose:** Spiritual/Vedantic text translation preserving tone
- **API Key:** `GEMINI_API_KEY` or `GOOGLE_API_KEY` (env var)

#### Fallback: Google Translate (via deep_translator)
- **Library:** `deep_translator.GoogleTranslator`
- **Purpose:** Free fallback when Gemini fails
- **No API key required**
- **Features:** Auto-detect source, supports English pivot for better quality

---

### 3. **VISION/CONTENT INTELLIGENCE** - Google Gemini
**File:** `dubber/vision_extractor.py`
- **Endpoint:** Google Generative Language API
- **Model:** `gemini-2.5-flash-lite`
- **Purpose:** Extract content intelligence from transcript:
  - main_topic (Gujarati, max 80 chars)
  - core_conflict (Gujarati, 1-2 sentences)
  - provocative_angle (Gujarati, 1 sentence)
  - festival, location, date (if mentioned)
  - theme (victory|celebration|devotional|teaching|announcement)
- **API Key:** `GEMINI_VISION_KEY` (env var)
- **Fallback:** Regex-based extraction from transcript
- **Output:** `vision.json`

---

### 4. **CAPTIONS** - OpenRouter (Llama)
**File:** `dubber/caption_generator.py`
- **Endpoint:** `https://openrouter.ai/api/v1/chat/completions`
- **Model:** `meta-llama/llama-3.3-70b-instruct:free`
- **Purpose:** Generate platform-specific captions (YouTube, Instagram, TikTok, Facebook, Twitter, Threads, Bluesky)
- **API Key:** Hardcoded in file (line 230) or `OPENROUTER_API_KEY` / `MISTRAL_API_KEY` (env var)
- **Features:**
  - JSON output with captions for all 7 platforms
  - Schema validation (missing/empty check)
  - Gujarati script validation
  - Character limit enforcement per platform
  - Retry for short captions
- **Fallback:** Template-based captions from vision data
- **Output:** `captions.json`, `caption_{platform}.txt`

---

### 5. **TTS (Text-to-Speech)** - Microsoft Azure
**File:** `dubber/tts_generator.py`
- **Endpoint:** Azure Edge TTS (unofficial)
- **Library:** `edge-tts`
- **Purpose:** Generate dubbed audio in target language
- **No API key required** (uses Azure's public edge endpoint)
- **Voices:**
  - Gujarati: `gu-IN-NiranjanNeural`, `gu-IN-DhwaniNeural`
  - Hindi: `hi-IN-MadhurNeural`, `hi-IN-SwaraNeural`
  - Tamil: `ta-IN-ValluvarNeural`, `ta-IN-PallaviNeural`
  - Telugu: `te-IN-MohanNeural`, `te-IN-ShrutiNeural`
  - English: `en-GB-RyanNeural`, `en-GB-SoniaNeural`
- **Output:** Individual `.mp3` files per segment

---

### 6. **PUBLISHING** - Zernio API
**File:** `dubber/publisher.py`
- **Base URL:** `https://zernio.com/api/v1`
- **Endpoints:**
  - `GET /accounts` - Validate platform account IDs
  - `POST /media/presign` - Get GCS upload URL
  - `PUT {uploadUrl}` - Upload media to Google Cloud Storage
  - `POST /posts` - Create posts on social platforms
- **Purpose:** Publish to 7 platforms (YouTube, Instagram, TikTok, Facebook, Twitter, Threads, Bluesky)
- **API Key:** `ZERNIO_API_KEY` (env var)
- **Features:**
  - Parallel async publishing
  - Duplicate guard (locks to prevent double-post)
  - Per-platform timeouts
  - Timeout-unconfirmed handling
  - Media upload to GCS before posting
- **Output:** `published.lock` (JSON with post IDs)

---

### 7. **GOOGLE SHEETS** - GSpread (Service Account)
**File:** `dubber/sheet_logger.py`
- **Scope:** `https://www.googleapis.com/auth/spreadsheets`
- **Purpose:** Log published video metadata to tracking sheet
- **Sheet Name:** `AutoDubQueue`
- **Authentication:** Service account JSON (`credentials.json`)
- **Columns:**
  - A: Video Title
  - B: Status ("Published ✅")
  - C: Attempts (auto-incremented)
  - D: YouTube URL
  - E: Duration
  - F: Source Lang
  - G: Target Lang
  - H: Platforms
  - I: Post IDs
  - J: Timestamp
- **Called:** After successful publish (integrated in `app.py`)

---

## Summary Table

| Stage | API | Model/Service | Key Env Var | Fallback |
|-------|-----|---------------|-------------|----------|
| Transcribe | Groq | whisper-large-v3 | `GROQ_API_KEY` | Local Whisper |
| Translate | Gemini | gemini-pro / gemini-1.5-flash | `GEMINI_API_KEY` | Google Translate (free) |
| Vision | Gemini | gemini-2.5-flash-lite | `GEMINI_VISION_KEY` | Regex extraction |
| Captions | OpenRouter | llama-3.3-70b-instruct | Hardcoded / `OPENROUTER_API_KEY` | Template-based |
| TTS | Azure | edge-tts | None (free) | N/A |
| Publish | Zernio | Zernio API | `ZERNIO_API_KEY` | N/A |
| Sheet Log | Google | gspread service account | `credentials.json` | N/A |

## API Key Summary (from .env)

```
GEMINI_API_KEY=xxx          # Translation
GEMINI_VISION_KEY=xxx       # Vision extraction
GROQ_API_KEY=xxx            # Transcription
ZERNIO_API_KEY=xxx          # Publishing
OPENROUTER_API_KEY=xxx      # Captions (or hardcoded)
NVIDIA_API_KEY=xxx          # (not currently used)
```

## Data Flow

1. **Video Input** → `transcribe_audio()` → Groq Whisper → `transcript.json`
2. **Segments** → `translate_segments()` → Gemini / Google Translate → Translated text
3. **Translated** → `extract_vision()` → Gemini Vision → `vision.json`
4. **Vision** → `generate_all_captions()` → OpenRouter Llama → `captions.json`
5. **Translated** → `generate_tts_audio()` → Azure Edge TTS → Audio files
6. **Audio+Video** → `build_dubbed_video()` → FFmpeg → `output.mp4`
7. **Video+Captions** → `publish_to_platforms_sdk()` → Zernio SDK → Published posts
8. **Results** → `quick_update_from_publish_result()` → Google Sheets → AutoDubQueue
