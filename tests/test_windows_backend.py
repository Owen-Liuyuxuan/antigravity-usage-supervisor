"""Exercise the settings protocol through the Windows client's Python entry point."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WindowsBackendTest(unittest.TestCase):
    def test_settings_round_trip_over_stdio(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = str(Path(temporary) / "用量")
            requests = [
                {"method": "settings/read"},
                {"method": "settings/write", "settings": {
                    "antigravity_home": data, "refresh_seconds": 55,
                }},
                {"method": "settings/read"},
            ]
            result = subprocess.run(
                [sys.executable, "-m", "antigravity_usage_supervisor.windows_backend"],
                input="".join(json.dumps(request) + "\n" for request in requests),
                env={**os.environ, "APPDATA": temporary, "XDG_CONFIG_HOME": temporary},
                capture_output=True, encoding="utf-8", check=True, timeout=10,
            )
            original, written, reloaded = map(json.loads, result.stdout.splitlines())
            self.assertEqual(original["result"]["refresh_seconds"], 30)
            self.assertEqual(written["result"]["antigravity_home"], data)
            self.assertEqual(written["result"]["refresh_seconds"], 55)
            self.assertEqual(written, reloaded)
