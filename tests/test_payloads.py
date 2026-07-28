from __future__ import annotations
import unittest
from imr_intruder.payloads import build_requests, generate_assignments, placeholders, render


class PayloadTests(unittest.TestCase):
    def test_placeholders_recursive(self):
        self.assertEqual(placeholders({"url":"/{{ID}}","json":{"u":"{{USER}}"}}), {"ID","USER"})

    def test_render_preserves_non_string_exact_value(self):
        self.assertEqual(render({"x":"{{VALUE}}"},{"VALUE":3}), {"x":3})

    def test_sniper(self):
        assignments=generate_assignments({"A":[1,2],"B":["x","y"]},"sniper")
        self.assertEqual(len(assignments),4)

    def test_pitchfork(self):
        self.assertEqual(generate_assignments({"A":[1,2],"B":[3,4]},"pitchfork"), [{"A":1,"B":3},{"A":2,"B":4}])

    def test_pitchfork_rejects_lengths(self):
        with self.assertRaises(ValueError): generate_assignments({"A":[1],"B":[2,3]},"pitchfork")

    def test_cluster_bomb_limit(self):
        with self.assertRaises(ValueError): generate_assignments({"A":[1,2],"B":[3,4]},"cluster-bomb",3)

    def test_build_requests_requires_payload(self):
        with self.assertRaises(ValueError): build_requests({"url":"/{{ID}}"},{"VALUE":[1]})
