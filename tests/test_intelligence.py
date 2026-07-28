from __future__ import annotations
import unittest
from imr_intruder.intelligence import body_hash, enrich_results, extract_value, normalize_body, rule_matches


class IntelligenceTests(unittest.TestCase):
    def test_json_normalization(self):
        self.assertEqual(normalize_body('{"b":2,"a":1}',"application/json"),'{"a":1,"b":2}')

    def test_volatile_hash(self):
        self.assertEqual(body_hash("token 0123456789abcdef0123456789abcdef"), body_hash("token fedcba9876543210fedcba9876543210"))

    def test_rules(self):
        result={"body_preview":"Welcome user=42","response_headers":{"X-ID":"abc"}}
        self.assertTrue(rule_matches("text:Welcome",result))
        self.assertTrue(rule_matches(r"regex:user=\d+",result))
        self.assertTrue(rule_matches("header:X-ID=abc",result))
        self.assertEqual(extract_value(r"regex:user=(\d+)",result),"42")

    def test_enrichment_clusters(self):
        rows=[{"status":200,"size_bytes":3,"elapsed_ms":10,"body_preview":"abc","content_type":"text/plain","custom":{}},{"status":302,"size_bytes":3,"elapsed_ms":20,"body_preview":"xyz","content_type":"text/plain","custom":{}}]
        enriched=enrich_results(rows,cluster_threshold=99)
        self.assertEqual(enriched[0]["cluster"],"C1")
        self.assertEqual(enriched[1]["cluster"],"C2")
        self.assertIn("anomaly_score",enriched[0])
