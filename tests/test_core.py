from __future__ import annotations
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from imr_intruder.core import execute_request, run_requests, write_csv


class Handler(BaseHTTPRequestHandler):
    hits = 0
    def log_message(self,*args): pass
    def do_GET(self):
        type(self).hits += 1
        if self.path.startswith('/redirect'):
            self.send_response(302); self.send_header('Location','/ok'); self.end_headers(); return
        body=json.dumps({'path':self.path,'token':'abc'}).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('X-Test','yes'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        length=int(self.headers.get('Content-Length','0')); content=self.rfile.read(length); body=b'posted:'+content
        self.send_response(201); self.send_header('Content-Type','text/plain'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler); cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start(); cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close()

    def test_get_and_column(self):
        result=execute_request(1,{'url':self.url+'/ok'},[{'name':'x','source':'header','key':'X-Test'}])
        self.assertEqual(result['status'],200); self.assertEqual(result['custom']['x'],'yes')

    def test_post_json(self):
        result=execute_request(1,{'url':self.url+'/post','method':'POST','json':{'a':1}})
        self.assertEqual(result['status'],201); self.assertIn('posted:',result['body_preview'])

    def test_redirect_not_followed(self):
        result=execute_request(1,{'url':self.url+'/redirect','follow_redirects':False})
        self.assertEqual(result['status'],302); self.assertEqual(result['location'],'/ok')

    def test_request_diagnostics_and_secret_redaction(self):
        result=execute_request(1,{"url":self.url+"/post","method":"POST","data":{"username":"alice","password":"secret"}})
        self.assertEqual(result["status"],201)
        self.assertEqual(result["outcome"],"http_response")
        self.assertTrue(result["response_received"])
        self.assertEqual(result["request_body_summary"]["username"],"alice")
        self.assertEqual(result["request_body_summary"]["password"],"<REDACTED>")
        self.assertIn("content-type",{key.lower() for key in result["request_headers"]})

    def test_single_response_has_no_meaningless_comparison(self):
        result=run_requests([{"url":self.url+"/single"}])[0]
        self.assertIsNone(result["similarity"])
        self.assertIsNone(result["cluster"])
        self.assertIsNone(result["anomaly_score"])

    def test_stale_content_length_is_removed_before_post(self):
        result=execute_request(1,{"url":self.url+"/post","method":"POST","headers":{"Content-Length":"1"},"data":{"username":"alice"}})
        self.assertEqual(result["status"],201)
        self.assertIn("username=alice",result["body_preview"])
        self.assertIn("Content-Length",result["removed_request_headers"])
        self.assertNotEqual(result["request_headers"].get("content-length"),"1")

    def test_pause_blocks_pending_start(self):
        import time
        pause=threading.Event(); pause.set(); holder=[]
        before=Handler.hits
        worker=threading.Thread(target=lambda: holder.extend(run_requests([{'url':self.url+'/paused'}],pause_event=pause)),daemon=True)
        worker.start(); time.sleep(0.15)
        self.assertEqual(Handler.hits,before)
        pause.clear(); worker.join(3)
        self.assertEqual(holder[0]['status'],200)

    def test_cancelled_result_has_complete_classification(self):
        cancel=threading.Event(); cancel.set()
        result=run_requests([{"url":self.url+"/cancelled"}],cancel_event=cancel)[0]
        self.assertEqual(result["outcome"],"cancelled")
        self.assertEqual(result["error_type"],"cancelled")
        self.assertFalse(result["response_received"])
        self.assertIsNone(result["similarity"])

    def test_cli_csv_contains_request_diagnostics(self):
        import tempfile
        from pathlib import Path
        result=execute_request(1,{"url":self.url+"/post","method":"POST","data":{"username":"alice"}})
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/"results.csv"
            write_csv(output,[result])
            header=output.read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertIn("outcome",header)
        self.assertIn("error_type",header)
        self.assertIn("request_size_bytes",header)

    def test_concurrent_enrichment(self):
        requests=[{'name':str(i),'url':self.url+f'/ok?i={i}'} for i in range(4)]
        results=run_requests(requests,workers=2,match_rules=['text:path'])
        self.assertEqual(len(results),4); self.assertTrue(all('cluster' in row for row in results))
