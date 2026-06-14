import unittest

from dubber.transcriber import (
    _annotate_opening_language_segments,
    _contains_non_latin_letters,
    _looks_like_spoken_text,
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
                "detected_language_probability": 0.97,
                "is_opening_recovery": True,
            }
        ]

        annotated = _annotate_opening_language_segments(segments)

        self.assertTrue(_contains_non_latin_letters(segments[0]["text"]))
        self.assertTrue(annotated[0]["preserve_original_audio"])

    def test_yoga_heavy_english_opening_is_not_preserved(self):
        # Regression: "yoga" is an ordinary content word in these talks, not a
        # scripture-citation marker. An English opening that merely says "yoga"
        # repeatedly must still be dubbed, not left in the original voice.
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 5.0,
                "text": "Chick Yoga, Cook Yoga. No! This is going to be my unique contribution",
                "detected_language": "en",
                "detected_language_probability": 1.0,
            }
        ]

        annotated = _annotate_opening_language_segments(segments)

        self.assertFalse(annotated[0]["preserve_original_audio"])

    def test_low_confidence_non_latin_opening_is_not_preserved(self):
        # Regression: English narration mis-transcribed by Whisper as Telugu
        # (transliterated into Telugu script) at low confidence must NOT be
        # left undubbed — otherwise the output starts in the source language
        # (English) and abruptly switches to the dub language a few seconds in.
        segments = [
            {
                "id": 0,
                "start": 0.0,
                "end": 12.0,
                "text": "దేర్ అల్లి టూ బియాస్స్ దాట్ రంగ్ యోర్ ర్యాలేట్",
                "detected_language": "te",
                "detected_language_probability": 0.67,
                "is_opening_recovery": True,
            }
        ]

        annotated = _annotate_opening_language_segments(segments)

        self.assertTrue(_contains_non_latin_letters(segments[0]["text"]))
        self.assertFalse(annotated[0]["preserve_original_audio"])

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


class NonSpeechHallucinationTests(unittest.TestCase):
    def test_caption_credit_hallucinations_are_dropped(self):
        # Regression: Whisper hallucinates caption/transcription credits over
        # trailing silence; these must be treated as non-speech so they are not
        # translated and dubbed as a stray clip at the end of the video.
        for phrase in (
            "© transcript Emily Beynon",
            "Transcribed by Jane Doe",
            "Subtitles by SomeOne",
            "Captions by ACME Media",
            "Subtitles by the Amara.org community",
        ):
            self.assertFalse(_looks_like_spoken_text(phrase), phrase)

    def test_genuine_speech_is_kept(self):
        for phrase in (
            "Chitta Suthi breaks that loop permanently.",
            "You can repair all the damage you lost.",
            "Let me transcribe my thoughts about this.",
            "આભાર. આ સૌથી શક્તિશાળી વૃદ્ધત્વ-વિરોધી પદ્ધતિ છે.",
        ):
            self.assertTrue(_looks_like_spoken_text(phrase), phrase)


if __name__ == "__main__":
    unittest.main()
