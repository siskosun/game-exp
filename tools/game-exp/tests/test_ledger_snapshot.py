from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

from ledger_snapshot import LedgerSnapshotLoader, SnapshotError  # noqa: E402


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.blobs = {
            "state.json": ("1" * 40, {"experiment_id": "EXP-1", "lifecycle": "ACTIVE"}),
            "manifest.json": ("2" * 40, {"title": "Prototype"}),
        }

    def __call__(self, command):
        self.calls.append(list(command))
        if any("/git/trees/" in arg for arg in command):
            value = {
                "truncated": False,
                "tree": [
                    {"type": "blob", "path": path, "sha": sha}
                    for path, (sha, _value) in self.blobs.items()
                ],
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(value), "")
        if "graphql" in command:
            expressions = [
                command[index + 1]
                for index, value in enumerate(command[:-1])
                if value == "-f" and command[index + 1].startswith("expr")
            ]
            repository = {}
            for index, entry in enumerate(expressions):
                _key, expression = entry.split("=", 1)
                _ref, path = expression.split(":", 1)
                sha, value = self.blobs[path]
                repository[f"b{index}"] = {
                    "oid": sha,
                    "text": json.dumps(value, separators=(",", ":")),
                }
            payload = {"data": {"repository": repository}}
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        raise AssertionError(command)


class LedgerSnapshotTests(unittest.TestCase):
    def test_snapshot_batches_and_reuses_memory_and_disk_cache(self):
        with tempfile.TemporaryDirectory() as td:
            runner = FakeRunner()
            loader = LedgerSnapshotLoader(
                "owner/repo",
                cache_root=Path(td),
                runner=runner,
            )
            ref = "a" * 40
            first = loader.load(ref)
            self.assertEqual(first.objects["state.json"]["lifecycle"], "ACTIVE")
            self.assertEqual(len(runner.calls), 2)

            second = loader.load(ref)
            self.assertIs(first, second)
            self.assertEqual(len(runner.calls), 2)

            cold_runner = FakeRunner()
            cold = LedgerSnapshotLoader(
                "owner/repo",
                cache_root=Path(td),
                runner=cold_runner,
            ).load(ref)
            self.assertEqual(cold.objects, first.objects)
            self.assertEqual(cold_runner.calls, [])

    def test_graphql_blob_identity_mismatch_fails_closed(self):
        class BadRunner(FakeRunner):
            def __call__(self, command):
                result = super().__call__(command)
                if "graphql" in command:
                    value = json.loads(result.stdout)
                    value["data"]["repository"]["b0"]["oid"] = "f" * 40
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps(value), ""
                    )
                return result

        with tempfile.TemporaryDirectory() as td:
            loader = LedgerSnapshotLoader(
                "owner/repo",
                cache_root=Path(td),
                runner=BadRunner(),
            )
            with self.assertRaises(SnapshotError):
                loader.load("b" * 40)


if __name__ == "__main__":
    unittest.main()
