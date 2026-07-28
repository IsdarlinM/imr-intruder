from __future__ import annotations
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from imr_intruder.updater import _clean_env, _safe_extract


def archive(files):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        for name,value in files.items(): z.writestr(name,value)
    return buf.getvalue()


class UpdaterTests(unittest.TestCase):
    def test_safe_extract(self):
        with tempfile.TemporaryDirectory() as temp:
            root=_safe_extract(archive({'project/pyproject.toml':'[project]\nname="x"'}),Path(temp))
            self.assertTrue((root/'pyproject.toml').is_file())

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError): _safe_extract(archive({'../x':'bad','project/pyproject.toml':'x'}),Path(temp))

    def test_clean_env(self):
        import os
        os.environ['PYTHONPATH']='bad'
        self.assertNotIn('PYTHONPATH',_clean_env())
