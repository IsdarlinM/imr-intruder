from __future__ import annotations

import unittest

from imr_intruder.importers import parse_curl, parse_har, parse_raw_request


class ImporterTests(unittest.TestCase):
    def test_raw_form(self):
        request = parse_raw_request(
            "POST /login HTTP/1.1\r\nHost: example.test\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\na=1&b=2"
        )
        self.assertEqual(request["url"], "https://example.test/login")
        self.assertEqual(request["data"], {"a": "1", "b": "2"})

    def test_raw_json(self):
        request = parse_raw_request(
            'POST https://example.test/api HTTP/1.1\nContent-Type: application/json\n\n{"x":1}'
        )
        self.assertEqual(request["json"], {"x": 1})

    def test_curl_headers_data(self):
        request = parse_curl(
            "curl -L -H 'Content-Type: application/json' -d '{\"x\":1}' https://example.test/api"
        )
        self.assertTrue(request["follow_redirects"])
        self.assertEqual(request["json"], {"x": 1})

    def test_curl_multipart(self):
        request = parse_curl("curl -F 'name=value' https://example.test/upload")
        self.assertEqual(request["multipart"], {"name": "value"})

    def test_har(self):
        data = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "method": "GET",
                            "url": "https://example.test/?a=1",
                            "headers": [],
                            "cookies": [],
                            "queryString": [{"name": "a", "value": "1"}],
                        }
                    }
                ]
            }
        }
        self.assertEqual(parse_har(data)[0]["params"], {"a": "1"})

    def test_curl_options_after_url_do_not_replace_target(self):
        request = parse_curl("curl https://example.test/path --connect-timeout 5 --retry=2")
        self.assertEqual(request["url"], "https://example.test/path")
        self.assertEqual(request["timeout"], 5)
        self.assertEqual(request["retries"], 2)

    def test_curl_inline_options_cookies_and_get_data(self):
        request = parse_curl(
            "curl -Gd'q=a%20b' -b 'session=abc; mode=test' -Aagent https://example.test/search"
        )
        self.assertEqual(request["method"], "GET")
        self.assertEqual(request["params"], {"q": "a b"})
        self.assertEqual(request["cookies"], {"session": "abc", "mode": "test"})
        self.assertEqual(request["headers"]["User-Agent"], "agent")

    def test_curl_rejects_unknown_or_truncated_options(self):
        with self.assertRaises(ValueError):
            parse_curl("curl --definitely-unsupported https://example.test")
        with self.assertRaises(ValueError):
            parse_curl("curl https://example.test --connect-timeout")
