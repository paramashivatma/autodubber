import os
import shutil
import unittest

from dubber.tts_generator import generate_tts_audio


class TTSGeneratorTests(unittest.TestCase):
    def test_preserved_segment_skips_tts_generation(self):
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 3.0,
                "text": "kshina kalmashah chinna dvaidha yatatmanah",
                "translated": "Gujarati translation that should not be spoken",
                "preserve_original_audio": True,
            }
        ]

        tmpdir = os.path.join("workspace", "test_tts_generator")
        shutil.rmtree(tmpdir, ignore_errors=True)
        os.makedirs(tmpdir, exist_ok=True)
        try:
            results = generate_tts_audio(segments, output_dir=tmpdir)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["preserve_original_audio"])
        self.assertTrue(results[0]["tts_skipped"])
        self.assertIsNone(results[0]["audio_path"])


if __name__ == "__main__":
    unittest.main()
