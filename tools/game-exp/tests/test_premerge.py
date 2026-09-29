from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import premerge  # noqa: E402


class PremergeTests(unittest.TestCase):
    def test_uv_managed_python_executes_mcp_tests(self):
        calls = []

        def fake_run(command):
            calls.append(command)
            return {
                "command": command,
                "returncode": 0,
                "output": "",
                "status": "PASS",
            }

        with (
            mock.patch("premerge.shutil.which", return_value="/usr/bin/uv"),
            mock.patch("premerge.run", side_effect=fake_run),
        ):
            result = premerge.premerge()

        self.assertEqual(result["status"], "PASS")
        self.assertGreaterEqual(len(calls), 3)
        self.assertEqual(
            calls[0][:5],
            ["/usr/bin/uv", "run", "--with", "mcp==2.2.0", "python"],
        )
        self.assertNotIn(sys.executable, calls[0][4:5])
        self.assertEqual(calls[0][5:8], ["-m", "unittest", "discover"])


if __name__ == "__main__":
    unittest.main()
