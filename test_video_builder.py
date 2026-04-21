import unittest

from dubber.video_builder import _segment_audio_strategy


class VideoBuilderTests(unittest.TestCase):
    def test_preserved_segment_uses_original_audio_strategy(self):
        strategy = _segment_audio_strategy(
            {"preserve_original_audio": True},
            orig_dur=3.2,
            tts_dur=1.8,
        )

        self.assertEqual(strategy["mode"], "original")
        self.assertEqual(strategy["target_dur"], 3.2)

    def test_normal_segment_uses_tts_audio_strategy(self):
        strategy = _segment_audio_strategy(
            {"preserve_original_audio": False},
            orig_dur=3.2,
            tts_dur=1.8,
        )

        self.assertEqual(strategy["mode"], "tts")
        self.assertEqual(strategy["target_dur"], 1.8)


if __name__ == "__main__":
    unittest.main()
