from __future__ import annotations

import pathlib
import contextlib
import json
import os
import re
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "game-exp-client-e2e.yml"
sys.path.insert(0, str(ROOT / "tools" / "game-exp"))

from domain_core import validate_manifest  # noqa: E402


class ClientE2EWorkflowContractTests(unittest.TestCase):
    def test_generated_canary_manifest_is_valid_for_current_domain(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        build_step = text.split("- name: Build stable supported bind request", 1)[1]
        build_step = build_step.split("- name: Submit real supported bind", 1)[0]
        source = re.search(r"python - <<'PY'\n(.*?)\n          PY", build_step, re.S)
        self.assertIsNotNone(source)
        env = dict(re.findall(r'^      (CANARY_[A-Z_]+): "([^"]+)"$', text, re.M))
        env.update(REPO_ID="1390906514", ISSUE_ID="5618053064", ISSUE_NUMBER="20")
        with tempfile.TemporaryDirectory() as temporary:
            with contextlib.chdir(temporary), patch.dict(os.environ, env):
                exec(compile(textwrap.dedent(source.group(1)), "canary-manifest", "exec"), {})
                inputs = json.loads(pathlib.Path("input.json").read_text(encoding="utf-8"))
        manifest = validate_manifest(inputs["manifest"])
        self.assertEqual(manifest["operation_id"], env["CANARY_REQUEST_ID"])
        self.assertEqual(manifest["parent"]["commit"], env["CANARY_PARENT_SHA"])

    def test_workflow_uses_supported_bind_operation(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("request experiment.bind", text)
        self.assertNotIn("experiment.create", text)
        self.assertIn('CANARY_REQUEST_ID: "req-client-e2e-bind-v1"', text)
        self.assertIn('CANARY_ISSUE_NUMBER: "20"', text)

    def test_workflow_requires_human_credential_for_live_write(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("GAME_EXP_E2E_TOKEN", text)
        self.assertIn("collaborators/$login/permission", text)
        self.assertIn("admin|maintain|write", text)

    def test_workflow_proves_applied_domain_result_and_exact_replay(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('record.get("domain_status")=="APPLIED"', text)
        self.assertIn('x["status"]=="COMMITTED"', text)
        self.assertIn('x.get("replayed") is True', text)
        self.assertIn('test "$before" = "$after"', text)


if __name__ == "__main__":
    unittest.main()
