from __future__ import annotations
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from fastapi.testclient import TestClient
from imr_intruder.collaboration import create_token
from imr_intruder.web import build_web_requests, create_app


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        body=f'path={self.path}'.encode(); self.send_response(200); self.send_header('Content-Type','text/plain'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler); cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start(); cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        self.token='test-token'; self.client=TestClient(create_app(self.token))

    def test_health_and_security_headers(self):
        response=self.client.get('/health'); self.assertEqual(response.status_code,200); self.assertEqual(response.headers['x-frame-options'],'DENY')

    def test_page_loads(self):
        response=self.client.get('/'); self.assertEqual(response.status_code,200); self.assertIn('imr-intruder',response.text)

    def test_api_requires_token(self):
        response=self.client.post('/api/jobs',json={'url':self.url}); self.assertEqual(response.status_code,403)

    def test_job_stream(self):
        payload={'url':self.url+'/{{VALUE}}','payloads':'a\nb','workers':2,'columns':'final=response:url'}
        response=self.client.post('/api/jobs',headers={'X-Request-Token':self.token},json=payload)
        self.assertEqual(response.status_code,202); job=response.json()['job_id']
        stream=self.client.get(f'/api/jobs/{job}/events',headers={'X-Request-Token':self.token})
        events=[json.loads(line) for line in stream.text.splitlines() if line.strip()]
        self.assertEqual(sum(event['event']=='result' for event in events),2); self.assertEqual(events[-1]['event'],'done')


    def test_remote_viewer_token_is_not_escalated(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            values={
                'IMR_INTRUDER_HOME':str(root/'home'),'IMR_INTRUDER_CONFIG':str(root/'config'),
                'IMR_INTRUDER_STATE':str(root/'state'),'IMR_INTRUDER_DATA':str(root/'data'),
                'IMR_INTRUDER_CACHE':str(root/'cache'),
            }
            with patch.dict(os.environ,values):
                viewer=create_token('viewer','viewer')
                operator=create_token('operator','operator')
                client=TestClient(create_app('admin-secret',require_page_token=True,multiuser=True))
                page=client.get('/?token='+viewer)
                self.assertEqual(page.status_code,200)
                self.assertIn(f'data-token="{viewer}"',page.text)
                self.assertNotIn('admin-secret',page.text)
                denied=client.post('/api/jobs',headers={'X-Request-Token':viewer},json={'url':self.url})
                self.assertEqual(denied.status_code,403)
                allowed=client.post('/api/jobs',headers={'X-Request-Token':operator},json={'url':self.url})
                self.assertEqual(allowed.status_code,202)

    def test_build_multiple_payload_sections(self):
        requests,_,_=build_web_requests({'url':self.url+'/?u={{USER}}&t={{TOKEN}}','payloads':'[USER]\na\nb\n[TOKEN]\nx\ny','mode':'pitchfork'})
        self.assertEqual(len(requests),2)
