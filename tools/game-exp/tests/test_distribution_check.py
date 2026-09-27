from __future__ import annotations

import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve()
TOOLS_DIR = HERE.parents[1]
ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from distribution_check import _command_matches, run_checks  # noqa: E402


class DistributionIntegrityTests(unittest.TestCase):
    def test_current_repository_distribution_contract_passes(self):
        result = run_checks(ROOT)
        failures = [
            row
            for row in result["checks"]
            if row["status"] != "PASS"
        ]
        self.assertEqual(failures, [])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(
            result["source"],
            "https://github.com/siskosun/game-exp",
        )

    def test_harness_command_contract_is_exact(self):
        self.assertTrue(
            _command_matches(
                [
                    "python",
                    "tools/game-exp/install_harnesses.py",
                    "--harness",
                    "codex",
                    "--json",
                ],
                "codex",
                check=False,
            )
        )
        self.assertTrue(
            _command_matches(
                [
                    "python",
                    "tools/game-exp/install_harnesses.py",
                    "--harness",
                    "cursor",
                    "--check",
                    "--json",
                ],
                "cursor",
                check=True,
            )
        )
        self.assertFalse(
            _command_matches(
                [
                    "python",
                    "tools/game-exp/install_harnesses.py",
                    "--harness",
                    "all",
                    "--json",
                ],
                "codex",
                check=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
