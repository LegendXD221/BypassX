import unittest

from api.main import URLValidationError, _validate_url


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


if __name__ == "__main__":
    unittest.main()
