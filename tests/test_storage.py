from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from imr_intruder.storage import (
    create_session,
    create_workspace,
    delete_session,
    export_workspace,
    list_sessions,
    list_workspaces,
    load_session,
    save_session,
    set_current_workspace,
)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.env = patch.dict(
            os.environ,
            {
                "IMR_INTRUDER_HOME": str(root / "home"),
                "IMR_INTRUDER_CONFIG": str(root / "config"),
                "IMR_INTRUDER_STATE": str(root / "state"),
                "IMR_INTRUDER_DATA": str(root / "data"),
                "IMR_INTRUDER_CACHE": str(root / "cache"),
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_session_lifecycle(self):
        create_session("lab")
        data = load_session("lab")
        data["headers"] = {"X": "1"}
        save_session("lab", data)
        self.assertEqual(list_sessions(), ["lab"])
        self.assertEqual(load_session("lab")["headers"], {"X": "1"})
        delete_session("lab")
        self.assertEqual(list_sessions(), [])

    def test_workspace_export(self):
        root = create_workspace("assessment")
        (root / "results" / "a.txt").write_text("x")
        set_current_workspace("assessment")
        output = Path(self.temp.name) / "export.tar.gz"
        export_workspace("assessment", output)
        self.assertEqual(list_workspaces(), ["assessment"])
        self.assertTrue(output.is_file())
