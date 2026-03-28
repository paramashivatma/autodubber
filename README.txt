v24 CHANGES
===========
1. caption_generator.py — Mistral replaces Gemini for captions.
   Full transcript passed into prompt — no more generic filler.
2. teaser_generator.py — drawtext overlay disabled cleanly.
   No more FFmpeg errors. Teasers cut clean first time every time.
3. app.py — UI updated: Gemini Caption Key -> Mistral API Key.
   segs passed to generate_all_captions for transcript-grounded output.

INSTALL
=======
pip install httpx python-dotenv

Place MISTRAL_API_KEY=your_key in .env
Copy these 3 files into your dubber_gui_v24 folder.
