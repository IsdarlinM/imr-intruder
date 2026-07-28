from __future__ import annotations
import unittest
from imr_intruder.importers import parse_curl, parse_har, parse_raw_request


class ImporterTests(unittest.TestCase):
    def test_raw_form(self):
        request=parse_raw_request("POST /login HTTP/1.1\r\nHost: example.test\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\na=1&b=2")
        self.assertEqual(request["url"],"https://example.test/login")
        self.assertEqual(request["data"],{"a":"1","b":"2"})

    def test_raw_json(self):
        request=parse_raw_request('POST https://example.test/api HTTP/1.1\nContent-Type: application/json\n\n{"x":1}')
        self.assertEqual(request["json"],{"x":1})

    def test_curl_headers_data(self):
        request=parse_curl("curl -L -H 'Content-Type: application/json' -d '{\"x\":1}' https://example.test/api")
        self.assertTrue(request["follow_redirects"])
        self.assertEqual(request["json"],{"x":1})

    def test_curl_multipart(self):
        request=parse_curl("curl -F 'name=value' https://example.test/upload")
        self.assertEqual(request["multipart"],{"name":"value"})

    def test_har(self):
        data={"log":{"entries":[{"request":{"method":"GET","url":"https://example.test/?a=1","headers":[],"cookies":[],"queryString":[{"name":"a","value":"1"}]}}]}}
        self.assertEqual(parse_har(data)[0]["params"],{"a":"1"})
