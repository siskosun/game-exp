from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "game-exp-client-e2e.yml"


class ClientE2EWorkflowContractTests(unittest.TestCase):
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
