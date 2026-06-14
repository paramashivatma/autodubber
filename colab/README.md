# Running AutoDubber on Google Colab (GPU)

`dubber_colab.ipynb` runs the dubbing pipeline on a free Colab GPU and gives you
`output.mp4` to download. It is **generation only** — it does not publish, so no
publishing credentials (YouTube/Bluesky/Zernio) are uploaded to Colab. The only
secret it needs is your **Gemini API key** (used for translation, and vision when
available).

## Why this is much faster than the laptop

The heavy stages are Whisper transcription and Demucs background separation,
which run on CPU locally. On a Colab T4 GPU they run roughly 10× faster. The code
picks the device from environment variables (defaulting to CPU, so the desktop
app is unchanged):

| Variable | Desktop default | Colab notebook sets |
|---|---|---|
| `WHISPER_DEVICE` | `cpu` | `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `float16` |
| `DEMUCS_DEVICE` | `cpu` | `cuda` |
| `DUB_VERIFICATION` | `0` (off) | `0` (off) |

## How to use

1. Open https://colab.research.google.com/ → **File → Upload notebook** → pick
   `colab/dubber_colab.ipynb` (or open it from GitHub).
2. **Runtime → Change runtime type → GPU (T4)**.
3. Run the cells top to bottom: check GPU → install → enter Gemini key → set the
   video URL + languages → run → download `output.mp4`.
4. Publish the downloaded file from the desktop app as usual.

## Notes / limitations

- Free Colab does not guarantee a GPU, disconnects after ~90 min idle, and wipes
  the filesystem each session — so you reinstall on every fresh session.
- If the GitHub repo is private, clone with a token:
  `!git clone https://<TOKEN>@github.com/paramashivatma/autodubber.git`
- This shares the same code as the desktop app, so any pipeline fix benefits both.
