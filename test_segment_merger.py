import unittest

from dubber.segment_merger import merge_short_segments


class SegmentMergerTrailingGarbageTests(unittest.TestCase):
    def test_keeps_plain_trailing_thank_you(self):
        segments = [
            {"id": 0, "start": 0.0, "end": 4.0, "text": "This is the main teaching."},
            {"id": 1, "start": 4.1, "end": 5.0, "text": "Thank you."},
        ]

        merged = merge_short_segments(segments)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "This is the main teaching. Thank you.")

    def test_keeps_trailing_nithyanandam(self):
        segments = [
            {"id": 0, "start": 0.0, "end": 4.0, "text": "This is the main teaching."},
            {"id": 1, "start": 4.1, "end": 5.0, "text": "Nithyanandam."},
        ]

        merged = merge_short_segments(segments)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "This is the main teaching. Nithyanandam.")

    def test_keeps_thank_you_when_nithyanandam_is_present(self):
        segments = [
            {"id": 0, "start": 0.0, "end": 4.0, "text": "This is the main teaching."},
            {"id": 1, "start": 4.1, "end": 5.4, "text": "Nithyanandam, thank you."},
        ]

        merged = merge_short_segments(segments)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "This is the main teaching. Nithyanandam, thank you.")

    def test_drops_obvious_trailing_dubbing_status(self):
        segments = [
            {"id": 0, "start": 0.0, "end": 4.0, "text": "This is the main teaching."},
            {"id": 1, "start": 5.5, "end": 6.2, "text": "Dubbing was done."},
        ]

        merged = merge_short_segments(segments)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "This is the main teaching.")

    def test_drops_trailing_amara_credit(self):
        segments = [
            {"id": 0, "start": 0.0, "end": 4.0, "text": "This is the main teaching."},
            {
                "id": 1,
                "start": 5.5,
                "end": 6.4,
                "text": "Subtitles by the Amara.org community.",
            },
        ]

        merged = merge_short_segments(segments)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "This is the main teaching.")


if __name__ == "__main__":
    unittest.main()
