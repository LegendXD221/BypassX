import unittest

from api.main import URLValidationError, _validate_url
from shortlink_bypass.bypass import get_handler


class ApiSecurityTests(unittest.TestCase):
    def test_accepts_public_http_url(self):
        self.assertEqual(_validate_url("https://example.com/path"), "https://example.com/path")

    def test_rejects_non_http_protocol(self):
        with self.assertRaises(URLValidationError):
            _validate_url("file:///etc/passwd")

    def test_rejects_loopback(self):
        with self.assertRaises(URLValidationError):
            _validate_url("http://127.0.0.1:8000/")

    def test_rejects_credentials(self):
        with self.assertRaises(URLValidationError):
            _validate_url("https://user:password@example.com/")

    def test_work_ink_is_classified_as_browser_only(self):
        handler, method = get_handler("https://work.ink/1YG/test")
        self.assertIsNone(handler)
        self.assertEqual(method, "fallback_only")

    def test_link_target_uses_specific_handler(self):
        handler, method = get_handler("https://link-target.net/abc/test")
        self.assertIsNotNone(handler)
        self.assertEqual(method, "specific")

    def test_lookalike_domain_does_not_match_linkvertise(self):
        handler, method = get_handler("https://notlinkvertise.com/abc/test")
        self.assertIsNotNone(handler)
        self.assertEqual(method, "generic")


if __name__ == "__main__":
    unittest.main()
