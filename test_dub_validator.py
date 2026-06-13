import unittest
import os
from unittest import mock

from dubber.dub_validator import verify_dubbed_output


class DubValidatorTests(unittest.TestCase):
    def test_incomplete_gujarati_verifier_transcript_is_non_blocking(self):
        segments = [
            {
                "translated": (
                    "તમે તમારા રોજિંદા જીવનમાં જ્યોતિષશાસ્ત્રનો ઉપયોગ કરી શકો છો. "
                    "ગુરુ યોજના બનાવશે અને તેને શક્ય બનાવશે."
                )
            }
        ]
        observed_segments = [
            {
                "start": 0.0,
                "end": 20.0,
                "text": "તમે તમારા રોજિંદા જીવનમાં જ્યોતિષશાસ્ત્રનો ઉપયોગ કરી શકો છો",
            }
        ]

        output_dir = os.path.abspath(os.path.join("workspace", "_test_dub_validator"))
        os.makedirs(output_dir, exist_ok=True)
        with mock.patch(
            "dubber.dub_validator._retranscribe_video_in_chunks",
            return_value=observed_segments,
        ):
            report = verify_dubbed_output(
                video_path="output.mp4",
                segments=segments,
                target_language="gu",
                output_dir=output_dir,
            )

        self.assertFalse(report["passed"])
        self.assertFalse(report["blocking_failure"])
        self.assertTrue(report["transcript_truncated"])

    def test_wrong_english_verifier_transcript_still_blocks(self):
        segments = [
            {
                "translated": (
                    "You can use astrology in your day to day life. "
                    "Guru will somehow plan and make it happen."
                )
            }
        ]
        observed_segments = [
            {
                "start": 0.0,
                "end": 6.0,
                "text": (
                    "This unrelated transcript has plenty of words but does not "
                    "match the expected dubbed script at all."
                ),
            }
        ]

        output_dir = os.path.abspath(os.path.join("workspace", "_test_dub_validator"))
        os.makedirs(output_dir, exist_ok=True)
        with mock.patch(
            "dubber.dub_validator._retranscribe_video_in_chunks",
            return_value=observed_segments,
        ):
            with self.assertRaises(RuntimeError):
                verify_dubbed_output(
                    video_path="output.mp4",
                    segments=segments,
                    target_language="en",
                    output_dir=output_dir,
                )


if __name__ == "__main__":
    unittest.main()
