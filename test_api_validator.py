import os
import unittest
from unittest import mock

from dubber.api_validator import _validate_mistral


class ApiValidatorTests(unittest.TestCase):
    def test_mistral_validation_skips_live_ping_by_default(self):
        with mock.patch.dict(os.environ, {"MISTRAL_VALIDATE_LIVE": "0"}):
            with mock.patch("requests.post") as post:
                result = _validate_mistral("test-key")

        self.assertEqual(result["status"], "ok")
        self.assertIn("skipped", result["message"])
        post.assert_not_called()

    def test_mistral_live_rate_limit_is_warning(self):
        class Response:
            status_code = 429
            text = "rate limited"

            def json(self):
                return {}

        with mock.patch.dict(os.environ, {"MISTRAL_VALIDATE_LIVE": "1"}):
            with mock.patch("requests.post", return_value=Response()):
                result = _validate_mistral("test-key")

        self.assertEqual(result["status"], "warning")
        self.assertIn("Rate limited", result["message"])


if __name__ == "__main__":
    unittest.main()
