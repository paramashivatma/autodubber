import unittest

from dubber.transcriber import (
    _annotate_opening_language_segments,
    _contains_non_latin_letters,
    _merge_opening_recovery_segments,
)
from dubber.segment_merger import merge_short_segments


class TranscriberMixedLanguageTests(unittest.TestCase):
    def test_opening_sanskrit_segment_is_preserved(self):
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 3.2,
                "text": "kshina kalmashah chinna dvaidha yatatmanah",
                "detected_language": "sa",
            }
        ]

        annotated = _annotate_opening_language_segments(segments)

        self.assertTrue(annotated[0]["preserve_original_audio"])

    def test_plain_english_opening_without_scripture_markers_is_not_preserved(self):
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.6,
                "text": "Welcome back everyone, today we are discussing inner freedom",
                "detected_language": "en",
            }
        ]

        annotated = _annotate_opening_language_segments(segments)

        self.assertFalse(annotated[0]["preserve_original_audio"])

    def test_scripture_opening_intro_is_preserved_in_original_voice(self):
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.6,
                "text": "In Bhagavad Gita 5th chapter Sannyasa Yoga 25th verse",
                "detected_language": "English",
            },
            {
                "id": 1,
                "start": 4.6,
                "end": 17.0,
                "text": "Translation",
                "detected_language": "English",
            },
        ]

        annotated = _annotate_opening_language_segments(segments)

        self.assertTrue(annotated[0]["preserve_original_audio"])
        self.assertTrue(annotated[1]["preserve_original_audio"])

    def test_non_latin_opening_segment_is_preserved_in_original_voice(self):
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.8,
                "text": "లబంతే బ్రమ్హ నిర్వానం",
                "detected_language": "Telugu",
            }
        ]

        annotated = _annotate_opening_language_segments(segments)

        self.assertTrue(_contains_non_latin_letters(segments[0]["text"]))
        self.assertTrue(annotated[0]["preserve_original_audio"])

    def test_opening_recovery_replaces_forced_english_lead(self):
        existing = [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.6,
                "text": "In Bhagavad Gita 5th chapter Sannyasa Yoga 25th verse",
                "detected_language": "en",
            },
            {
                "id": 1,
                "start": 4.6,
                "end": 8.0,
                "text": "Translation",
                "detected_language": "en",
            },
        ]
        recovered = [
            {
                "id": 0,
                "start": 0.0,
                "end": 3.8,
                "text": "kshina kalmashah chinna dvaidha yatatmanah",
                "detected_language": "sa",
            }
        ]

        merged = _merge_opening_recovery_segments(existing, recovered, 10.0)

        self.assertEqual(merged[0]["text"], "kshina kalmashah chinna dvaidha yatatmanah")
        self.assertTrue(merged[0]["preserve_original_audio"])
        self.assertEqual(merged[1]["text"], "Translation")

    def test_merge_preserves_original_audio_flag(self):
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.6,
                "text": "In Bhagavad Gita 5th chapter Sannyasa Yoga 25th verse",
                "detected_language": "English",
                "preserve_original_audio": True,
            },
            {
                "id": 1,
                "start": 4.6,
                "end": 17.0,
                "text": "Translation",
                "detected_language": "English",
                "preserve_original_audio": True,
            },
        ]

        merged = merge_short_segments(segments)

        self.assertTrue(all(seg["preserve_original_audio"] for seg in merged))


if __name__ == "__main__":
    unittest.main()
