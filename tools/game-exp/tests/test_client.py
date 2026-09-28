from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

from client import (  # noqa: E402
    ClientError,
    GameExpClient,
    TransportUncertainError,
    _runtime_version,
)
from protocol_core import digest_object  # noqa: E402
from trust_policy import ruleset_templates  # noqa: E402


class FakeTransport:
    repo = "owner/repo"

    def __init__(self):
        self.head = "a" * 40
        self.dispatched = []
        self.record = None
        self.records = {}
        self.execution_runs = {}
        self.request_runs = {}
        self.state = None
        self.logs = ""
        self.dispatch_uncertain = False
        self._ledger_json = {}
        self._ledger_paths = []
        self._ledger_json_refs = []
        self._git_refs = {}
        self._compare_commits = {}
        self._tag_objects = {}
        self._rules = [
            {"name": "game-exp ledger", "enforcement": "active"},
            {"name": "game-exp experiment branches", "enforcement": "active"},
            {"name": "game-exp immutable refs", "enforcement": "active"},
            {"name": "game-exp protected main", "enforcement": "active"},
        ]

    def ledger_head(self):
        return self.head

    def compare_commits(self, base_sha, head_sha):
        return self._compare_commits.get(
            (base_sha, head_sha),
            {"status": "behind"},
        )

    def write_principals(self):
        return ["owner"]

    def repository_access(self):
        return {
            "status": "WRITE",
            "can_read": True,
            "can_write": True,
            "can_admin": False,
            "admin_coverage": "PARTIAL",
            "reason": None,
            "repository_id": "1384446218",
            "visibility": "public",
            "private": False,
            "default_branch": "main",
            "owner_type": "User",
        }

    def repository_json(self, path, ref=None):
        if path == "plugins/game-exp/plugin.json":
            return {"version": _runtime_version()}
        if path == ".game-exp/project-policy.json":
            return {
                "schema_version": 2,
                "adapter": "node-npm",
                "toolchain": {"node_version": "22.21.1"},
                "install": {"argv": ["npm", "ci"]},
                "test": {"argv": ["npm", "test"]},
                "build": {"argv": ["npm", "run", "build"]},
                "candidate": {
                    "include": ["dist"],
                    "required_paths": ["dist/index.html"],
                },
            }
        return None

    def collaborator_permission(self, login):
        return "write" if login in {"alice", "bob", "carol"} else None

    def branch_contributors(self, ref):
        if ref in {"exp/7", "exp-final/7"}:
            return {
                "contributors": ["alice", "bob"],
                "source": "github_commits",
                "complete": True,
            }
        if ref in {"exp/21", "exp-final/21"}:
            return {
                "contributors": ["carol"],
                "source": "github_commits",
                "complete": True,
            }
        return {
            "contributors": [],
            "source": "github_commits",
            "complete": True,
        }

    def dispatch_writer(self, **kwargs):
        self.dispatched.append(kwargs)
        if self.dispatch_uncertain:
            raise TransportUncertainError("network outcome unknown")
        return "https://github.com/owner/repo/actions/runs/123"

    def dispatch_execution(
        self,
        *,
        action,
        experiment_id,
        request_id,
        arguments=None,
    ):
        self.dispatched.append(
            {
                "execution": action,
                "experiment_id": experiment_id,
                "request_id": request_id,
                "arguments": arguments or {},
            }
        )
        if self.dispatch_uncertain:
            raise TransportUncertainError("network outcome unknown")
        return "https://github.com/owner/repo/actions/runs/900"

    def find_execution_run(self, *, action, request_id):
        return self.execution_runs.get((action, request_id))

    def find_request_runs(self, request_id):
        return list(self.request_runs.get(request_id, []))

    def dispatch_initializer(self, experiment_id):
        self.dispatched.append({"initializer": experiment_id})
        if self.dispatch_uncertain:
            raise TransportUncertainError("network outcome unknown")
        return "https://github.com/owner/repo/actions/runs/456"

    def dispatch_candidate(self, experiment_id):
        self.dispatched.append({"candidate": experiment_id})
        if self.dispatch_uncertain:
            raise TransportUncertainError("network outcome unknown")
        return "https://github.com/owner/repo/actions/runs/788"

    def dispatch_rehearsal(self, experiment_id):
        self.dispatched.append({"rehearsal": experiment_id})
        if self.dispatch_uncertain:
            raise TransportUncertainError("network outcome unknown")
        return "https://github.com/owner/repo/actions/runs/789"

    def dispatch_integration(self, experiment_id):
        self.dispatched.append({"integration": experiment_id})
        if self.dispatch_uncertain:
            raise TransportUncertainError("network outcome unknown")
        return "https://github.com/owner/repo/actions/runs/790"

    def dispatch_integration_finalize(self, experiment_id, pr_number):
        self.dispatched.append(
            {"integration_finalize": experiment_id, "pr_number": str(pr_number)}
        )
        if self.dispatch_uncertain:
            raise TransportUncertainError("network outcome unknown")
        return "https://github.com/owner/repo/actions/runs/791"

    def dispatch_archive(self, experiment_id, mode):
        self.dispatched.append({"archive": experiment_id, "mode": mode})
        if self.dispatch_uncertain:
            raise TransportUncertainError("network outcome unknown")
        return "https://github.com/owner/repo/actions/runs/792"

    def ledger_paths(self, ref):
        self.last_ledger_paths_ref = ref
        return list(self._ledger_paths)

    def ledger_json(self, path, *, ref=None):
        self._ledger_json_refs.append((path, ref))
        return self._ledger_json.get(path)

    def git_ref(self, ref_path):
        return self._git_refs.get(ref_path)

    def annotated_tag(self, tag_object_sha):
        return self._tag_objects[tag_object_sha]

    def ledger_record(self, request_id):
        return self.records.get(request_id, self.record)

    def run_state(self, workflow_url):
        return self.state

    def failed_run_logs(self, workflow_url):
        return self.logs

    def rulesets(self):
        return self._rules

    def ruleset_details(self):
        return {
            row["name"]: row
            for row in ruleset_templates("single-principal")
        }

    def environment_branch_policies(self, environment):
        return [{"id": 1, "name": "main", "type": "branch"}]

    def environment_secret_names(self, environment):
        return {"GAME_EXP_WRITER_KEY"}

    def deploy_keys(self):
        return [{"title": "game-exp trusted writer", "read_only": False}]

    def secret_names(self):
        return set()

    def immutable_releases(self):
        return {"enabled": True, "enforced_by_owner": False}


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch("client._journal_root", return_value=self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def _add_valid_board_binding(
        self,
        transport: FakeTransport,
        experiment_id: str,
        manifest: dict,
    ):
        request_id = "req_bind_" + experiment_id.lower().replace("-", "_")
        payload = {
            "kind": "operation_request",
            "schema_version": 1,
            "operation": "experiment.bind",
            "input": {"manifest": manifest},
            "preconditions": {},
        }
        digest = digest_object(payload)
        issue = experiment_id.removeprefix("EXP-")
        initiator = "alice" if experiment_id == "EXP-7" else "carol"
        transport._ledger_json[f"experiments/{experiment_id}/binding.json"] = {
            "request_id": request_id,
            "inputs_digest": digest,
            "initiator": {
                "login": initiator,
                "user_id": "1001" if initiator == "alice" else "1003",
                "permission_at_bind": "write",
            },
            "initialization": {
                "manifest_digest": digest_object(manifest),
                "branch_ref": f"refs/heads/exp/{issue}",
                "final_tag_ref": f"refs/tags/exp-final/{issue}",
            },
        }
        transport._ledger_json[f"operations/{request_id}.json"] = {
            "request_id": request_id,
            "payload_digest": digest,
            "payload": payload,
        }
        return request_id

    def test_cross_machine_reconcile_discovers_writer_run_without_local_journal(self):
        transport = FakeTransport()
        transport.request_runs["req_cross_machine"] = [
            {
                "databaseId": 700,
                "displayTitle": "game-exp:request:req_cross_machine:ignored",
                "status": "in_progress",
                "conclusion": None,
                "url": "https://github.com/owner/repo/actions/runs/700",
                "payloadDigest": "sha256:" + "1" * 64,
                "expectedHead": "a" * 40,
            }
        ]
        result = GameExpClient(transport).reconcile("req_cross_machine")
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(result["operation_status"], "WRITER_RUNNING")
        self.assertEqual(result["payload_digest"], "sha256:" + "1" * 64)

    def test_same_cross_machine_request_does_not_dispatch_second_writer(self):
        transport = FakeTransport()
        payload = {
            "kind": "operation_request",
            "schema_version": 1,
            "operation": "experiment.create",
            "input": {"hypothesis": "same"},
            "preconditions": {},
        }
        digest = digest_object(payload)
        transport.request_runs["req_cross_same"] = [
            {
                "databaseId": 701,
                "displayTitle": "game-exp request",
                "status": "in_progress",
                "conclusion": None,
                "url": "https://github.com/owner/repo/actions/runs/701",
                "payloadDigest": digest,
                "expectedHead": "a" * 40,
            }
        ]
        result = GameExpClient(transport).submit(
            operation="experiment.create",
            input_value={"hypothesis": "same"},
            request_id="req_cross_same",
        )
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(transport.dispatched, [])

    def test_cross_machine_same_id_different_payload_conflicts_before_redispatch(self):
        transport = FakeTransport()
        first_payload = {
            "kind": "operation_request",
            "schema_version": 1,
            "operation": "experiment.create",
            "input": {"hypothesis": "first"},
            "preconditions": {},
        }
        transport.request_runs["req_cross_conflict"] = [
            {
                "databaseId": 702,
                "displayTitle": "game-exp request",
                "status": "completed",
                "conclusion": "failure",
                "url": "https://github.com/owner/repo/actions/runs/702",
                "payloadDigest": digest_object(first_payload),
                "expectedHead": "a" * 40,
            }
        ]
        result = GameExpClient(transport).submit(
            operation="experiment.create",
            input_value={"hypothesis": "different"},
            request_id="req_cross_conflict",
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["conflict_type"], "REQUEST_ID_CONFLICT")
        self.assertEqual(transport.dispatched, [])

    def test_cross_machine_writer_run_preserves_original_head_conflict(self):
        transport = FakeTransport()
        transport.request_runs["req_cross_head"] = [
            {
                "databaseId": 703,
                "displayTitle": "game-exp request",
                "status": "completed",
                "conclusion": "failure",
                "url": "https://github.com/owner/repo/actions/runs/703",
                "payloadDigest": "sha256:" + "2" * 64,
                "expectedHead": "a" * 40,
            }
        ]
        transport.logs = '{"status":"HEAD_CONFLICT"}'
        result = GameExpClient(transport).reconcile("req_cross_head")
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["conflict_type"], "HEAD_CONFLICT")
        self.assertEqual(result["expected_head"], "a" * 40)

    def test_submit_then_reconcile_committed(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        result = client.submit(
            operation="experiment.create",
            input_value={"hypothesis": "three roles"},
            request_id="req_test_1",
        )
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(len(transport.dispatched), 1)

        payload = {
            "kind": "operation_request",
            "schema_version": 1,
            "operation": "experiment.create",
            "input": {"hypothesis": "three roles"},
            "preconditions": {},
        }
        transport.record = {
            "request_id": "req_test_1",
            "payload_digest": digest_object(payload),
            "payload": payload,
        }
        reconciled = client.reconcile("req_test_1")
        self.assertEqual(reconciled["status"], "COMMITTED")
        self.assertTrue(reconciled["verified_against_local_request"])

    def test_submit_replay_returns_committed_without_second_dispatch(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        first = client.submit(
            operation="experiment.create",
            input_value={"hypothesis": "three roles"},
            request_id="req_test_replay",
        )
        self.assertEqual(first["status"], "ACCEPTED")
        self.assertEqual(len(transport.dispatched), 1)

        payload = {
            "kind": "operation_request",
            "schema_version": 1,
            "operation": "experiment.create",
            "input": {"hypothesis": "three roles"},
            "preconditions": {},
        }
        transport.record = {
            "request_id": "req_test_replay",
            "payload_digest": digest_object(payload),
            "payload": payload,
        }

        replay = client.submit(
            operation="experiment.create",
            input_value={"hypothesis": "three roles"},
            request_id="req_test_replay",
        )
        self.assertEqual(replay["status"], "COMMITTED")
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(transport.dispatched), 1)

    def test_remote_digest_mismatch_is_conflict(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        client.submit(
            operation="experiment.create",
            input_value={"hypothesis": "three roles"},
            request_id="req_test_2",
        )
        transport.record = {
            "request_id": "req_test_2",
            "payload_digest": "sha256:" + "0" * 64,
        }
        reconciled = client.reconcile("req_test_2")
        self.assertEqual(reconciled["status"], "CONFLICT")
        self.assertEqual(reconciled["conflict_type"], "REQUEST_ID_CONFLICT")

    def test_failed_workflow_maps_head_conflict(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        client.submit(
            operation="experiment.create",
            input_value={},
            request_id="req_test_3",
        )
        transport.state = {
            "status": "completed",
            "conclusion": "failure",
            "url": "https://github.com/owner/repo/actions/runs/123",
        }
        transport.logs = '{"status":"HEAD_CONFLICT"}'
        reconciled = client.reconcile("req_test_3")
        self.assertEqual(reconciled["status"], "CONFLICT")
        self.assertEqual(reconciled["conflict_type"], "HEAD_CONFLICT")


    def test_failed_workflow_maps_domain_identity_conflict(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        client.submit(
            operation="experiment.bind",
            input_value={"manifest": {"placeholder": True}},
            request_id="req_test_domain_conflict",
        )
        transport.state = {
            "status": "completed",
            "conclusion": "failure",
            "url": "https://github.com/owner/repo/actions/runs/123",
        }
        transport.logs = '{"status":"DOMAIN_IDENTITY_CONFLICT","error":"trusted identity mismatch"}'
        reconciled = client.reconcile("req_test_domain_conflict")
        self.assertEqual(reconciled["status"], "CONFLICT")
        self.assertEqual(reconciled["conflict_type"], "DOMAIN_IDENTITY_CONFLICT")

    def test_failed_workflow_maps_domain_invalid_to_rejected(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        client.submit(
            operation="experiment.bind",
            input_value={"manifest": {"placeholder": True}},
            request_id="req_test_domain_invalid",
        )
        transport.state = {
            "status": "completed",
            "conclusion": "failure",
            "url": "https://github.com/owner/repo/actions/runs/123",
        }
        transport.logs = '{"status":"DOMAIN_INVALID","error":"invalid manifest"}'
        reconciled = client.reconcile("req_test_domain_invalid")
        self.assertEqual(reconciled["status"], "REJECTED")
        self.assertEqual(reconciled["domain_error"], "DOMAIN_INVALID")

    def test_uncertain_dispatch_keeps_original_expected_head_for_retry(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        transport.dispatch_uncertain = True

        first = client.submit(
            operation="experiment.create",
            input_value={"hypothesis": "retry me"},
            request_id="req_test_uncertain",
        )
        self.assertEqual(first["status"], "UNKNOWN")
        original_head = first["expected_head"]

        transport.head = "b" * 40
        transport.dispatch_uncertain = False
        second = client.submit(
            operation="experiment.create",
            input_value={"hypothesis": "retry me"},
            request_id="req_test_uncertain",
        )
        self.assertEqual(second["status"], "ACCEPTED")
        self.assertEqual(transport.dispatched[-1]["expected_head"], original_head)

    def test_same_local_request_id_with_different_payload_is_conflict(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        client.submit(
            operation="experiment.create",
            input_value={"hypothesis": "A"},
            request_id="req_test_local_conflict",
        )
        result = client.submit(
            operation="experiment.create",
            input_value={"hypothesis": "B"},
            request_id="req_test_local_conflict",
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["conflict_type"], "LOCAL_REQUEST_ID_CONFLICT")

    def test_status_is_compact_version_and_access_handshake(self):
        transport = FakeTransport()
        result = GameExpClient(transport).status()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["ledger_head"], transport.head)
        self.assertEqual(result["runtime_version"], _runtime_version())
        self.assertEqual(result["repository_version"], _runtime_version())
        self.assertEqual(result["version_state"], "MATCH")
        self.assertEqual(result["access"]["status"], "WRITE")

    def test_write_is_blocked_when_runtime_and_repository_versions_differ(self):
        transport = FakeTransport()
        original = transport.repository_json

        def repository_json(path, ref=None):
            if path == "plugins/game-exp/plugin.json":
                return {"version": "9.0.0"}
            return original(path, ref=ref)

        transport.repository_json = repository_json
        result = GameExpClient(transport).submit(
            operation="experiment.bind",
            input_value={"manifest": {"operation_id": "req_version_guard"}},
            request_id="req_version_guard",
        )
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["code"], "VERSION_MISMATCH")
        self.assertEqual(result["required_action"], "UPGRADE_CURRENT_HARNESS")
        self.assertEqual(transport.dispatched, [])

    def test_write_is_unknown_when_version_cannot_be_verified(self):
        transport = FakeTransport()
        original = transport.repository_json

        def repository_json(path, ref=None):
            if path == "plugins/game-exp/plugin.json":
                raise TransportUncertainError("temporary API failure")
            return original(path, ref=ref)

        transport.repository_json = repository_json
        result = GameExpClient(transport).submit(
            operation="experiment.bind",
            input_value={"manifest": {"operation_id": "req_version_unknown"}},
            request_id="req_version_unknown",
        )
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["code"], "VERSION_UNVERIFIED")
        self.assertTrue(result["retryable"])
        self.assertEqual(transport.dispatched, [])

    def test_access_check_reports_write_and_read_only(self):
        transport = FakeTransport()
        result = GameExpClient(transport).access_check()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["can_create_experiment"])
        self.assertEqual(result["access"]["status"], "WRITE")
        self.assertEqual(result["access"]["visibility"], "public")
        self.assertEqual(result["access"]["default_branch"], "main")
        self.assertIn("读写权限", result["message_zh"])

        transport.repository_access = lambda: {
            "status": "READ_ONLY",
            "can_read": True,
            "can_write": False,
            "can_admin": False,
            "admin_coverage": "PARTIAL",
            "reason": None,
        }
        readonly = GameExpClient(transport).access_check()
        self.assertEqual(readonly["status"], "PASS")
        self.assertFalse(readonly["can_create_experiment"])
        self.assertIn("只有读取权限", readonly["message_zh"])


    def test_experiment_template_is_self_describing_from_current_repository(self):
        result = GameExpClient(FakeTransport()).experiment_template()

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["manifest_contract"]["current_schema_version"], 3)
        self.assertEqual(
            result["manifest_contract"]["supported_schema_versions"],
            [1, 2, 3],
        )
        self.assertEqual(result["manifest_contract"]["recommended_schema_version"], 2)
        self.assertEqual(result["project_policy"]["schema_version"], 2)
        self.assertEqual(result["project_policy"]["adapter"], "node-npm")
        self.assertEqual(
            result["project_policy"]["toolchain"],
            {"node_version": "22.21.1"},
        )
        self.assertEqual(
            result["project_policy"]["builtin_runner_setup"],
            "actions/setup-node",
        )
        self.assertEqual(
            result["defaults"]["runtime"],
            {
                "adapter": "node-npm",
                "policy_path": ".game-exp/project-policy.json",
            },
        )
        self.assertEqual(
            result["defaults"]["review"]["protocol"],
            "manual-playtest-v1",
        )
        self.assertEqual(
            result["example_manifest"]["experiment"]["repository_id"],
            "1384446218",
        )
        self.assertEqual(result["example_manifest"]["schema_version"], 2)
        self.assertNotIn("evaluation_profile", result["example_manifest"])
        self.assertFalse(result["defaults"]["evaluation_enabled"])
        self.assertFalse(result["example_manifest_bindable"])
        self.assertIn("不要搜索其他仓库", result["next_zh"])
        self.assertNotIn("toy2game", str(result))

    def test_experiment_template_reports_missing_project_policy(self):
        transport = FakeTransport()
        transport.repository_json = lambda path, ref=None: None
        result = GameExpClient(transport).experiment_template()
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["code"], "PROJECT_POLICY_MISSING")

    def test_experiment_get_projects_current_domain_objects(self):
        transport = FakeTransport()
        transport._ledger_json["experiments/EXP-21/state.json"] = {
            "experiment_id": "EXP-21",
            "lifecycle": "ARCHIVED",
            "current_candidate_id": "C-21-1-1",
            "current_review_id": "req_review",
            "current_rehearsal_id": "R-21-2-1",
            "current_integration_id": "I-21-PR-3",
            "current_archive_id": "A-21-1",
        }
        transport._ledger_json["experiments/EXP-21/binding.json"] = {"kind": "experiment_identity"}
        transport._ledger_json["experiments/EXP-21/manifest.json"] = {"schema_version": 1}
        transport._ledger_json["experiments/EXP-21/candidates/C-21-1-1.json"] = {"candidate_id": "C-21-1-1"}
        transport._ledger_json["experiments/EXP-21/reviews/req_review.json"] = {"review_id": "req_review"}
        transport._ledger_json["experiments/EXP-21/rehearsals/R-21-2-1.json"] = {"rehearsal_id": "R-21-2-1"}
        transport._ledger_json["experiments/EXP-21/integrations/I-21-PR-3.json"] = {"integration_id": "I-21-PR-3"}
        transport._ledger_json["experiments/EXP-21/archives/A-21-1.json"] = {"archive_id": "A-21-1"}

        result = GameExpClient(transport).experiment_get("EXP-21")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["state"]["lifecycle"], "ARCHIVED")
        self.assertEqual(result["candidate"]["candidate_id"], "C-21-1-1")
        self.assertEqual(result["review"]["review_id"], "req_review")
        self.assertEqual(result["rehearsal"]["rehearsal_id"], "R-21-2-1")
        self.assertEqual(result["integration"]["integration_id"], "I-21-PR-3")
        self.assertEqual(result["archive"]["archive_id"], "A-21-1")

    def test_experiment_get_returns_unknown_for_missing_experiment(self):
        result = GameExpClient(FakeTransport()).experiment_get("EXP-99")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["reason"], "experiment_not_found_in_ledger")

    def test_board_projects_consistent_lightweight_snapshot(self):
        transport = FakeTransport()
        transport._ledger_paths = [
            "experiments/EXP-7/state.json",
            "experiments/EXP-7/manifest.json",
            "experiments/EXP-21/state.json",
            "experiments/EXP-21/manifest.json",
            "experiments/EXP-21/reviews/req_review.json",
            "operations/req_other.json",
        ]
        transport._ledger_json.update(
            {
                "experiments/EXP-7/state.json": {
                    "experiment_id": "EXP-7",
                    "lifecycle": "REVIEW",
                    "current_candidate_id": "C-7-1-1",
                    "current_review_id": None,
                    "archive_lock": None,
                },
                "experiments/EXP-7/manifest.json": {
                    "title": "Combat readability",
                    "subject": {
                        "type": "game-prototype",
                        "id": "arena-duel",
                        "name": "Arena Duel",
                        "root_path": "games/arena-duel",
                    },
                    "hypothesis": "roles improve readability",
                    "success_criteria": ["turn ownership is clearer"],
                    "kill_criteria": ["cue slows successful streaks"],
                    "experiment": {"issue_number": "7"},
                    "scope": {"allowed": ["games/arena-duel/**"]},
                    "relationships": [
                        {"type": "depends_on", "experiment_id": "EXP-21"},
                    ],
                    "created_at": "2026-09-24T10:00:00Z",
                },
                "experiments/EXP-21/state.json": {
                    "experiment_id": "EXP-21",
                    "lifecycle": "ARCHIVED",
                    "current_candidate_id": "C-21-1-1",
                    "current_review_id": "req_review",
                    "current_rehearsal_id": "R-21-2-1",
                    "current_integration_id": "I-21-PR-3",
                    "current_archive_id": "A-21-1",
                    "archive_lock": None,
                },
                "experiments/EXP-21/manifest.json": {
                    "title": "Binding pilot",
                    "hypothesis": "trusted binding works",
                    "experiment": {"issue_number": "21"},
                    "scope": {"allowed": ["games/**"]},
                    "created_at": "2026-09-24T11:00:00Z",
                },
                "experiments/EXP-21/reviews/req_review.json": {
                    "review_id": "req_review",
                    "outcome": "PASS",
                },
            }
        )

        self._add_valid_board_binding(
            transport,
            "EXP-7",
            transport._ledger_json["experiments/EXP-7/manifest.json"],
        )
        self._add_valid_board_binding(
            transport,
            "EXP-21",
            transport._ledger_json["experiments/EXP-21/manifest.json"],
        )

        result = GameExpClient(transport).board()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["snapshot_head"], transport.head)
        self.assertEqual(result["count"], 2)
        self.assertEqual(
            result["counts_by_lifecycle"],
            {"ARCHIVED": 1, "REVIEW": 1},
        )
        self.assertEqual(result["counts_by_health"], {"PASS": 2})
        self.assertEqual(
            [row["experiment_id"] for row in result["experiments"]],
            ["EXP-7", "EXP-21"],
        )
        self.assertEqual(
            result["experiments"][0]["next_gate"],
            "HUMAN_REVIEW",
        )
        self.assertEqual(
            result["experiments"][1]["next_gate"],
            "TERMINAL_NEW_EXPERIMENT_FOR_NEW_WORK",
        )
        self.assertEqual(result["experiments"][1]["review_outcome"], "PASS")
        self.assertEqual(result["repo"], "owner/repo")
        self.assertEqual(result["repository_name"], "repo")
        self.assertEqual(result["repository"]["visibility"], "public")
        self.assertEqual(result["repository"]["visibility_zh"], "公开")
        self.assertEqual(result["repository"]["default_branch"], "main")
        self.assertEqual(result["project"]["readiness"], "PROJECT_READY")
        self.assertEqual(result["project"]["doctor_status"], "PASS")
        self.assertEqual(result["project"]["repository_check_status"], "PASS")
        self.assertEqual(result["project"]["repository_check_status_zh"], "正常")
        self.assertEqual(
            result["project"]["repository_check"]["label_zh"],
            "仓库检查",
        )
        self.assertEqual(
            result["project"]["repository_check"]["status_zh"],
            "正常",
        )
        self.assertEqual(result["project"]["access"], "WRITE")
        self.assertTrue(result["project"]["can_create_experiment"])
        self.assertEqual(result["project"]["next_action"], "OPEN_ATTENTION")
        self.assertEqual(result["project"]["next_action_zh"], "处理需要你关注的实验")
        self.assertEqual(result["statistics"]["total"], 2)
        self.assertEqual(result["statistics"]["active"], 1)
        self.assertEqual(result["statistics"]["archived"], 1)
        self.assertEqual(result["statistics"]["abandoned"], 0)
        self.assertEqual(result["statistics"]["attention"], 1)
        self.assertEqual(result["statistics"]["abnormal_health"], 0)
        self.assertEqual(
            result["statistics"]["attention_sections"],
            [{"section": "REVIEW", "title_zh": "需要你评审", "count": 1}],
        )
        self.assertFalse(result["onboarding"]["active"])
        self.assertIn("项目已就绪", result["display"]["project_status_zh"])
        self.assertEqual(result["display"]["next_action_zh"], "处理需要你关注的实验")
        self.assertEqual(result["experiments"][0]["repository"], "owner/repo")
        self.assertEqual(result["experiments"][0]["repository_name"], "repo")
        self.assertEqual(result["experiments"][0]["prototype_name"], "Arena Duel")
        self.assertEqual(result["experiments"][0]["subject_id"], "arena-duel")
        self.assertEqual(result["experiments"][0]["subject_source"], "manifest")
        self.assertEqual(result["experiments"][0]["initiator"]["login"], "alice")
        self.assertEqual(result["experiments"][0]["contributors"], ["alice", "bob"])
        self.assertEqual(result["experiments"][0]["contributors_source"], "github_commits")
        self.assertTrue(result["experiments"][0]["contributors_complete"])
        card = result["experiments"][0]["card_zh"]
        self.assertEqual(card["locale"], "zh-CN")
        self.assertEqual(card["prototype_zh"], "Arena Duel")
        self.assertEqual(card["initiator_zh"], "alice")
        self.assertEqual(card["contributors_zh"], "alice\u3001bob")
        self.assertEqual(card["branch_zh"], "refs/heads/exp/7")
        self.assertEqual(card["progress_zh"], "\u8bc4\u5ba1\u4e2d")
        self.assertEqual(card["health_zh"], "\u6b63\u5e38")
        self.assertEqual(
            card["next_action_zh"],
            "\u63d0\u4ea4\u4eba\u5de5\u8bc4\u5ba1\u7ed3\u679c\uff08\u901a\u8fc7 / \u672a\u901a\u8fc7\uff09",
        )
        self.assertEqual(
            [row["label"] for row in card["rows_zh"]],
            ["\u5b9e\u9a8c", "\u539f\u578b", "\u53d1\u8d77\u4eba", "\u4ee3\u7801\u8d21\u732e\u8005", "\u5206\u652f", "\u8fdb\u5c55", "\u5065\u5eb7", "\u4e0b\u4e00\u6b65"],
        )
        self.assertNotIn("REVIEW", card["summary_text_zh"])
        self.assertNotIn("PASS", card["summary_text_zh"])
        self.assertEqual(result["experiments"][1]["initiator"]["login"], "carol")
        self.assertEqual(result["experiments"][1]["contributors"], ["carol"])
        self.assertEqual(result["experiments"][1]["prototype_name"], "仓库级/未指定原型")
        self.assertEqual(result["experiments"][1]["subject_source"], "scope-fallback")
        self.assertEqual(result["attention_count"], 1)
        self.assertEqual(
            result["views"]["overview"],
            {
                "attention_ids": ["EXP-7"],
                "active_ids": ["EXP-7"],
                "abandoned_ids": [],
                "archived_count": 1,
            },
        )
        self.assertEqual(
            result["views"]["attention"]["experiment_ids"],
            ["EXP-7"],
        )
        self.assertEqual(
            result["views"]["attention"]["sections"],
            [
                {
                    "section": "REVIEW",
                    "title_zh": "需要你评审",
                    "count": 1,
                    "experiment_ids": ["EXP-7"],
                }
            ],
        )
        self.assertEqual(
            result["experiments"][0]["display"],
            {
                "lifecycle": "评审中",
                "health": "正常",
                "next_gate": "人工评审",
                "attention_section": "需要你评审",
                "attention_reason": "等待人工评审",
                "attention_action": "提交人工评审结果（通过 / 未通过）",
            },
        )
        self.assertEqual(
            result["views"]["prototypes"]["groups"][0]["subject"]["name"],
            "Arena Duel",
        )
        self.assertEqual(
            result["views"]["prototypes"]["groups"][0]["attention_count"],
            1,
        )
        self.assertEqual(
            result["views"]["prototypes"]["relationship_edges"][0]["type_zh"],
            "依赖",
        )
        self.assertEqual(
            result["experiments"][0]["relationships_outgoing"][0][
                "target_experiment_id"
            ],
            "EXP-21",
        )
        self.assertEqual(
            result["experiments"][0]["dependency_reviews"][0]["code"],
            "DEPENDENCY_REVIEW_REQUIRED",
        )
        self.assertFalse(
            result["experiments"][0]["dependency_reviews"][0]["blocks_progress"]
        )
        self.assertEqual(
            result["experiments"][1]["relationships_incoming"][0]["type_zh"],
            "被依赖",
        )
        self.assertTrue(
            all(
                isinstance(event["label_zh"], str)
                and event["label_zh"]
                for event in result["experiments"][1]["activity"]
            )
        )
        self.assertIn(
            "已归档",
            [event["label_zh"] for event in result["experiments"][1]["activity"]],
        )
        self.assertEqual(
            result["views"]["branches"]["lanes"][0]["experiment_id"],
            "EXP-7",
        )
        self.assertEqual(
            result["views"]["branches"]["lanes"][0]["lifecycle_zh"],
            "评审中",
        )
        self.assertEqual(
            result["views"]["archive"]["experiment_ids"],
            ["EXP-21"],
        )
        self.assertEqual(result["experiments"][0]["health"], "PASS")
        self.assertEqual(result["experiments"][1]["health"], "PASS")
        self.assertEqual(transport.last_ledger_paths_ref, transport.head)
        self.assertTrue(transport._ledger_json_refs)
        self.assertTrue(
            all(ref == transport.head for _path, ref in transport._ledger_json_refs)
        )
        notifications = GameExpClient(transport).notification_feed(viewer_login="bob")
        self.assertEqual(notifications["status"], "PASS")
        created = next(
            row
            for row in notifications["notifications"]
            if row["experiment_id"] == "EXP-7"
            and row["event_code"] == "EXPERIMENT_CREATED"
        )
        self.assertEqual(created["actor_login"], "alice")
        self.assertIn("bob", created["targets"])
        self.assertNotIn("alice", created["targets"])
        self.assertEqual(created["delivery"]["dedupe_key"], created["event_id"])
        self.assertFalse(
            notifications["delivery_contract"]["game_exp_sends_messages"]
        )

        handoff = GameExpClient(transport).prototype_handoff("EXP-7")
        self.assertEqual(handoff["status"], "PASS")
        self.assertEqual(handoff["handoff_target"], "godot-prototype-studio")
        self.assertEqual(handoff["handoff_schema_version"], 2)
        executor = handoff["recommended_executor"]
        self.assertEqual(executor["id"], "godot-prototype-studio")
        self.assertEqual(
            executor["source_url"],
            "https://github.com/siskosun/godot-prototype-studio",
        )
        self.assertTrue(executor["recommended"])
        self.assertFalse(executor["required"])
        self.assertFalse(executor["missing_is_blocking"])
        self.assertFalse(executor["affects_experiment_health"])
        self.assertTrue(executor["check_before_implementation"])
        self.assertEqual(executor["availability_resolved_by"], "host")
        self.assertIn("不是必需依赖", executor["missing_prompt_zh"])
        self.assertIn("不安装也可以", executor["missing_prompt_zh"])
        self.assertEqual(handoff["source"]["branch_ref"], "refs/heads/exp/7")
        self.assertEqual(handoff["brief"]["hypothesis"], "roles improve readability")
        self.assertIn("source_sha", handoff["return_contract"]["required"])
        self.assertIn("artifacts", handoff["return_contract"]["required"])
        self.assertIn("build_identity", handoff["return_contract"]["required"])

        self.assertEqual(
            result["focus"],
            {
                "active": False,
                "query": None,
                "subject_id": None,
                "lifecycle": None,
                "attention_only": False,
                "count": 2,
                "attention_count": 1,
                "counts_by_lifecycle": {"ARCHIVED": 1, "REVIEW": 1},
                "counts_by_health": {"PASS": 2},
                "experiment_ids": ["EXP-7", "EXP-21"],
                "summary_zh": "全部 2 个实验，其中 1 个需要处理",
            },
        )

        focused = GameExpClient(transport).board(
            query="combat",
            subject_id="arena-duel",
            lifecycle="review",
            attention_only=True,
        )
        self.assertEqual(focused["count"], 2)
        self.assertEqual(focused["focus"]["count"], 1)
        self.assertEqual(focused["focus"]["experiment_ids"], ["EXP-7"])
        self.assertEqual(focused["focus"]["lifecycle"], "REVIEW")
        self.assertEqual(focused["focus"]["attention_count"], 1)
        self.assertEqual(focused["focus"]["counts_by_lifecycle"], {"REVIEW": 1})
        self.assertEqual(focused["focus"]["counts_by_health"], {"PASS": 1})
        self.assertEqual(
            focused["focus"]["summary_zh"],
            "已聚焦 1 个实验，其中 1 个需要处理",
        )

        panel = GameExpClient(transport).experiment_panel("EXP-7")
        self.assertEqual(panel["status"], "PASS")
        self.assertEqual(panel["snapshot_head"], transport.head)
        self.assertEqual(panel["overview"]["title"], "Combat readability")
        self.assertEqual(panel["overview"]["lifecycle_zh"], "评审中")
        self.assertEqual(panel["overview"]["next_action_zh"], "人工评审")
        self.assertEqual(panel["overview"]["initiator"]["login"], "alice")
        self.assertEqual(panel["overview"]["contributors"], ["alice", "bob"])
        self.assertEqual(
            panel["judgement"],
            {
                "hypothesis": "roles improve readability",
                "success_criteria": ["turn ownership is clearer"],
                "kill_criteria": ["cue slows successful streaks"],
            },
        )
        self.assertEqual(
            panel["relationships"]["outgoing"][0]["target_experiment_id"],
            "EXP-21",
        )
        self.assertEqual(panel["evidence"]["candidate_id"], "C-7-1-1")

        missing = GameExpClient(transport).experiment_panel("EXP-999")
        self.assertEqual(missing["status"], "UNKNOWN")
        self.assertEqual(missing["reason"], "experiment_not_found_in_ledger")

        invalid = GameExpClient(transport).experiment_panel("exp/7")
        self.assertEqual(invalid["status"], "REJECTED")
        self.assertEqual(invalid["reason"], "invalid_experiment_id")

        subject_panel = GameExpClient(transport).subject_panel("arena-duel")
        self.assertEqual(subject_panel["status"], "PASS")
        self.assertEqual(subject_panel["snapshot_head"], transport.head)
        self.assertEqual(subject_panel["subject"]["name"], "Arena Duel")
        self.assertEqual(
            subject_panel["summary"],
            {
                "count": 1,
                "active_count": 1,
                "abandoned_count": 0,
                "archived_count": 0,
                "attention_count": 1,
                "relationship_count": 1,
                "counts_by_lifecycle": {"REVIEW": 1},
                "counts_by_health": {"PASS": 1},
            },
        )
        self.assertEqual(
            subject_panel["experiments"][0]["experiment_id"],
            "EXP-7",
        )
        self.assertEqual(
            subject_panel["relationship_edges"][0]["target_experiment_id"],
            "EXP-21",
        )

        missing_subject = GameExpClient(transport).subject_panel("missing")
        self.assertEqual(missing_subject["status"], "UNKNOWN")
        self.assertEqual(missing_subject["reason"], "subject_not_found_in_ledger")

        invalid_subject = GameExpClient(transport).subject_panel("   ")
        self.assertEqual(invalid_subject["status"], "REJECTED")
        self.assertEqual(invalid_subject["reason"], "invalid_subject_id")

    def test_empty_board_exposes_project_ready_first_experiment_onboarding(self):
        transport = FakeTransport()
        result = GameExpClient(transport).board()

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["project"]["readiness"], "PROJECT_READY")
        self.assertTrue(result["project"]["complete"])
        self.assertEqual(result["project"]["doctor_status"], "PASS")
        self.assertEqual(
            result["project"]["next_action"],
            "CREATE_FIRST_EXPERIMENT",
        )
        self.assertEqual(
            result["project"]["next_action_zh"],
            "创建第一个实验",
        )
        self.assertEqual(result["statistics"]["total"], 0)
        self.assertEqual(result["statistics"]["active"], 0)
        self.assertEqual(result["statistics"]["archived"], 0)
        self.assertEqual(result["statistics"]["attention"], 0)
        self.assertEqual(result["statistics"]["abnormal_health"], 0)
        self.assertTrue(result["onboarding"]["active"])
        self.assertEqual(result["onboarding"]["progress"], "2/6")
        self.assertEqual(result["onboarding"]["title_zh"], "描述第一个实验")
        self.assertEqual(
            result["onboarding"]["primary_action"],
            "CREATE_FIRST_EXPERIMENT",
        )
        self.assertEqual(result["display"]["empty_state_zh"], "暂无实验")
        self.assertEqual(
            result["display"]["next_action_zh"],
            "创建第一个实验",
        )
        self.assertNotIn("project-init", result["project"]["message_zh"])

    def test_board_display_contract_uses_natural_chinese_without_machine_codes(self):
        transport = FakeTransport()
        result = GameExpClient(transport).board()
        display = result["display"]

        self.assertEqual(result["presentation"]["contract_version"], 6)
        self.assertEqual(result["presentation"]["primary"], "display")
        self.assertEqual(
            result["presentation"]["primary_text_path"],
            "display.summary_text_zh",
        )
        self.assertEqual(result["presentation"]["locale"], "zh-CN")
        self.assertTrue(result["presentation"]["copy_is_ready_to_render"])
        self.assertTrue(result["presentation"]["strict_primary_copy"])
        self.assertTrue(result["presentation"]["raw_fields_are_diagnostics"])
        self.assertEqual(result["presentation"]["experiment_card_path"], "experiments[].card_zh")
        self.assertTrue(result["presentation"]["experiment_cards_ready_to_render"])
        self.assertEqual(
            result["presentation"]["forbidden_primary_tokens"],
            display["render_contract"]["forbidden_primary_tokens"],
        )
        self.assertEqual(display["locale"], "zh-CN")
        self.assertEqual(display["presentation_version"], 6)
        self.assertTrue(display["raw_machine_codes_hidden_by_default"])
        self.assertEqual(
            [row["label"] for row in display["rows_zh"]],
            [
                "仓库",
                "项目状态",
                "我的权限",
                "实验记录快照",
                "实验统计",
                "下一步",
            ],
        )
        self.assertEqual(
            display["rows_zh"][1]["value"],
            "项目已就绪 · 仓库检查：正常",
        )
        self.assertEqual(
            display["rows_zh"][2]["value"],
            "可读写 · 可创建实验",
        )
        self.assertEqual(display["trust_title_zh"], "仓库检查")
        self.assertIn("实验记录：正常", display["trust_summary_zh"])
        self.assertIn("分支与引用保护：正常", display["trust_summary_zh"])
        self.assertIn("可信写入部署密钥：正常", display["trust_summary_zh"])
        self.assertIn("可信写入私钥：正常", display["trust_summary_zh"])
        self.assertIn("发布保护：正常", display["trust_summary_zh"])
        render_contract = display["render_contract"]
        self.assertEqual(render_contract["primary_copy"], "display")
        self.assertEqual(
            render_contract["primary_text"],
            "display.summary_text_zh",
        )
        self.assertEqual(
            render_contract["summary_rows"],
            "display.rows_zh",
        )
        self.assertEqual(
            render_contract["trust_summary"],
            "display.trust_summary_zh",
        )
        self.assertEqual(render_contract["raw_fields"], "logic_only")
        self.assertEqual(render_contract["machine_codes"], "diagnostics_only")
        self.assertFalse(render_contract["translate_machine_keys"])
        self.assertTrue(render_contract["strict_primary_copy"])
        self.assertIn("医生检查", render_contract["forbidden_primary_tokens"])
        self.assertIn("PROJECT_READY", render_contract["forbidden_primary_tokens"])
        self.assertIn("PASS", render_contract["forbidden_primary_tokens"])
        self.assertEqual(display["terminology_zh"]["doctor"], "仓库检查")
        self.assertEqual(display["terminology_zh"]["ledger"], "实验记录")
        self.assertEqual(
            display["trust_checks_zh"][0],
            {"label": "实验记录", "value": "正常"},
        )
        self.assertIn("项目状态：项目已就绪 · 仓库检查：正常", display["summary_text_zh"])

        visible = "\n".join(
            [
                display["title_zh"],
                *(f"{row['label']}：{row['value']}" for row in display["rows_zh"]),
                display["trust_title_zh"],
                display["trust_summary_zh"],
                display["snapshot_note_zh"],
                display["summary_text_zh"],
            ]
        )
        for forbidden in display["render_contract"]["forbidden_primary_tokens"]:
            self.assertNotIn(forbidden, visible)

    def test_board_display_contract_hides_read_only_machine_enum(self):
        transport = FakeTransport()
        transport.repository_access = lambda: {
            "status": "READ_ONLY",
            "can_read": True,
            "can_write": False,
            "can_admin": False,
            "admin_coverage": "PARTIAL",
            "reason": "read only",
            "repository_id": "1384446218",
            "visibility": "private",
            "private": True,
            "default_branch": "main",
            "owner_type": "User",
        }
        result = GameExpClient(transport).board()
        display = result["display"]
        self.assertEqual(
            display["rows_zh"][0]["value"],
            "owner/repo · 私有 · 默认分支 main",
        )
        self.assertEqual(
            display["rows_zh"][2]["value"],
            "只读 · 不可创建实验",
        )
        visible = "\n".join(
            [
                display["summary_text_zh"],
                display["trust_summary_zh"],
                *(f"{row['label']}：{row['value']}" for row in display["rows_zh"]),
            ]
        )
        for forbidden in display["render_contract"]["forbidden_primary_tokens"]:
            self.assertNotIn(forbidden, visible)

    def test_board_doctor_cache_reuses_recent_repo_health(self):
        client = GameExpClient(FakeTransport())
        with patch.object(
            client,
            "doctor",
            return_value={"status": "PASS", "checks": []},
        ) as doctor:
            first = client._repo_doctor_cached()
            second = client._repo_doctor_cached()
        self.assertIs(first, second)
        doctor.assert_called_once_with()

    def test_surface_hint_is_compact_for_normal_progress(self):
        hint = GameExpClient._board_surface_hint(
            {"required": False, "reason": None, "action_zh": None},
            "IMPLEMENT_OR_REVIEW",
        )
        self.assertEqual(hint["mode"], "COMPACT_RESULT")
        self.assertFalse(hint["surface_when_relevant"])
        self.assertFalse(hint["authoritative"])

    def test_surface_hint_uses_contextual_panel_for_human_gate(self):
        hint = GameExpClient._board_surface_hint(
            {
                "required": True,
                "reason": "HUMAN_REVIEW",
                "action_zh": "提交人工评审结果（通过 / 未通过）",
            },
            "HUMAN_REVIEW",
        )
        self.assertEqual(hint["mode"], "CONTEXTUAL_PANEL")
        self.assertTrue(hint["surface_when_relevant"])
        self.assertEqual(hint["reason"], "HUMAN_REVIEW")
        self.assertFalse(hint["authoritative"])

    def test_empty_board_failed_doctor_routes_to_project_repair(self):
        transport = FakeTransport()
        transport.ruleset_details = lambda: {}
        result = GameExpClient(transport).board()

        self.assertEqual(result["project"]["readiness"], "PROJECT_INCOMPLETE")
        self.assertFalse(result["project"]["complete"])
        self.assertEqual(result["project"]["doctor_status"], "FAIL")
        self.assertEqual(result["project"]["next_action"], "REPAIR_PROJECT")
        self.assertEqual(
            result["project"]["next_action_zh"],
            "修复仓库信任检查失败项",
        )
        self.assertTrue(result["onboarding"]["active"])
        self.assertEqual(result["onboarding"]["progress"], "1/6")
        self.assertEqual(result["onboarding"]["title_zh"], "连接检查")
        display = result["display"]
        self.assertEqual(
            display["rows_zh"][1]["value"],
            "项目未就绪 · 仓库检查：异常",
        )
        visible = "\n".join(
            [
                display["summary_text_zh"],
                display["trust_summary_zh"],
                *(f"{row['label']}：{row['value']}" for row in display["rows_zh"]),
            ]
        )
        for forbidden in display["render_contract"]["forbidden_primary_tokens"]:
            self.assertNotIn(forbidden, visible)

    def test_board_marks_archive_lock_as_recovery_gate(self):
        transport = FakeTransport()
        transport._ledger_paths = ["experiments/EXP-9/state.json"]
        transport._ledger_json.update(
            {
                "experiments/EXP-9/state.json": {
                    "experiment_id": "EXP-9",
                    "lifecycle": "INTEGRATED",
                    "archive_lock": {"archive_id": "A-9-1", "phase": "CLAIMED"},
                },
                "experiments/EXP-9/manifest.json": {
                    "title": "Archive recovery",
                    "hypothesis": "recover same archive",
                    "experiment": {"issue_number": "9"},
                },
            }
        )
        self._add_valid_board_binding(
            transport,
            "EXP-9",
            transport._ledger_json["experiments/EXP-9/manifest.json"],
        )
        result = GameExpClient(transport).board()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["experiments"][0]["health"], "PASS")
        self.assertEqual(result["experiments"][0]["next_gate"], "ARCHIVE_RECOVERY")

    def test_board_blocks_corrupted_binding_request_digest(self):
        transport = FakeTransport()
        manifest = {
            "title": "Corrupt pilot",
            "hypothesis": "must not be actionable",
            "experiment": {"issue_number": "19"},
        }
        transport._ledger_paths = [
            "experiments/EXP-19/state.json",
            "experiments/EXP-19/manifest.json",
            "experiments/EXP-19/binding.json",
        ]
        transport._ledger_json["experiments/EXP-19/state.json"] = {
            "experiment_id": "EXP-19",
            "lifecycle": "ACTIVE",
            "archive_lock": None,
        }
        transport._ledger_json["experiments/EXP-19/manifest.json"] = manifest
        request_id = self._add_valid_board_binding(transport, "EXP-19", manifest)
        transport._ledger_json[f"operations/{request_id}.json"]["payload"]["input"][
            "manifest"
        ]["title"] = "mutated after digest"

        result = GameExpClient(transport).board()
        row = result["experiments"][0]
        self.assertEqual(row["health"], "FAIL")
        self.assertEqual(
            row["health_code"],
            "BINDING_REQUEST_PAYLOAD_DIGEST_MISMATCH",
        )
        self.assertEqual(row["next_gate"], "DO_NOT_USE_RECREATE_EXPERIMENT")
        self.assertTrue(row["attention"]["required"])
        self.assertEqual(row["attention"]["priority"], 0)
        self.assertEqual(row["attention"]["reason"], "HEALTH_FAIL")
        self.assertEqual(result["views"]["attention"]["experiment_ids"], ["EXP-19"])
        self.assertEqual(result["counts_by_health"], {"FAIL": 1})

    def test_abandon_submits_direct_terminal_decision_without_review(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        with (
            patch.object(
                client,
                "experiment_get",
                return_value={
                    "status": "PASS",
                    "state": {"lifecycle": "ACTIVE", "last_decision_id": "req_prev"},
                },
            ),
            patch.object(
                client,
                "submit",
                return_value={"status": "ACCEPTED"},
            ) as submit,
        ):
            result = client.abandon(
                "EXP-21",
                "product priority changed",
                request_id="req_abandon_21",
                actor_claim="alice",
            )
        self.assertEqual(result["status"], "ACCEPTED")
        submit.assert_called_once_with(
            operation="experiment.decision",
            input_value={
                "experiment_id": "EXP-21",
                "to_state": "ABANDONED",
                "previous_decision_id": "req_prev",
                "reason": "product priority changed",
            },
            actor_claim="alice",
            request_id="req_abandon_21",
        )

    def test_board_excludes_abandoned_from_active_and_marks_archive_next(self):
        transport = FakeTransport()
        manifest = {
            "title": "Stopped prototype",
            "subject": {
                "type": "game-prototype",
                "id": "stopped-proto",
                "name": "Stopped Proto",
                "root_path": "games/stopped",
            },
            "hypothesis": "test",
            "success_criteria": ["works"],
            "kill_criteria": ["fails"],
            "experiment": {"issue_number": "31"},
            "scope": {"allowed": ["games/stopped/**"]},
            "created_at": "2026-09-27T00:00:00Z",
        }
        transport._ledger_paths = [
            "experiments/EXP-31/state.json",
            "experiments/EXP-31/manifest.json",
            "experiments/EXP-31/binding.json",
        ]
        transport._ledger_json["experiments/EXP-31/state.json"] = {
            "experiment_id": "EXP-31",
            "lifecycle": "ABANDONED",
            "archive_lock": None,
            "last_decision_id": "req_abandon_31",
        }
        transport._ledger_json["experiments/EXP-31/manifest.json"] = manifest
        self._add_valid_board_binding(transport, "EXP-31", manifest)

        result = GameExpClient(transport).board()
        self.assertEqual(result["status"], "PASS")
        row = result["experiments"][0]
        self.assertEqual(row["lifecycle"], "ABANDONED")
        self.assertEqual(row["display"]["lifecycle"], "已终止")
        self.assertEqual(row["next_gate"], "ARCHIVE")
        self.assertEqual(result["views"]["overview"]["active_ids"], [])
        self.assertEqual(result["views"]["overview"]["abandoned_ids"], ["EXP-31"])
        self.assertEqual(result["statistics"]["abandoned"], 1)
        self.assertEqual(
            result["views"]["prototypes"]["groups"][0]["abandoned_count"],
            1,
        )

    def test_async_wrappers_route_through_stable_execution_contract(self):
        client = GameExpClient(FakeTransport())
        cases = [
            (
                lambda: client.candidate(
                    "EXP-21",
                    request_id="req_candidate_21",
                    actor_claim="ignored-transport-metadata",
                ),
                {
                    "action": "candidate_build",
                    "experiment_id": "EXP-21",
                    "request_id": "req_candidate_21",
                    "actor_claim": "ignored-transport-metadata",
                },
            ),
            (
                lambda: client.initialize(
                    "EXP-21",
                    request_id="req_init_21",
                ),
                {
                    "action": "initialize",
                    "experiment_id": "EXP-21",
                    "request_id": "req_init_21",
                    "actor_claim": None,
                },
            ),
            (
                lambda: client.rehearse(
                    "EXP-21",
                    request_id="req_rehearse_21",
                ),
                {
                    "action": "rehearse",
                    "experiment_id": "EXP-21",
                    "request_id": "req_rehearse_21",
                    "actor_claim": None,
                },
            ),
            (
                lambda: client.integrate(
                    "EXP-21",
                    request_id="req_integrate_21",
                ),
                {
                    "action": "integrate",
                    "experiment_id": "EXP-21",
                    "request_id": "req_integrate_21",
                    "actor_claim": None,
                },
            ),
        ]
        for invoke, expected in cases:
            with self.subTest(action=expected["action"]):
                with patch.object(
                    client,
                    "start_execution",
                    return_value={"status": "ACCEPTED"},
                ) as start_execution:
                    result = invoke()
                self.assertEqual(result["status"], "ACCEPTED")
                start_execution.assert_called_once_with(**expected)

    def test_integrate_finalize_and_archive_route_exact_arguments(self):
        client = GameExpClient(FakeTransport())
        with patch.object(
            client,
            "start_execution",
            return_value={"status": "ACCEPTED"},
        ) as start_execution:
            result = client.integrate_finalize(
                "EXP-21",
                "77",
                request_id="req_finalize_21",
            )
        self.assertEqual(result["status"], "ACCEPTED")
        start_execution.assert_called_once_with(
            action="integrate_finalize",
            experiment_id="EXP-21",
            request_id="req_finalize_21",
            arguments={"pr_number": "77"},
            actor_claim=None,
        )

        with patch.object(
            client,
            "start_execution",
            return_value={"status": "ACCEPTED"},
        ) as start_execution:
            result = client.archive(
                "EXP-21",
                "ATOMIC_DELETE",
                request_id="req_archive_21",
            )
        self.assertEqual(result["status"], "ACCEPTED")
        start_execution.assert_called_once_with(
            action="archive",
            experiment_id="EXP-21",
            request_id="req_archive_21",
            arguments={"mode": "ATOMIC_DELETE"},
            actor_claim=None,
        )

    def test_async_validation_rejects_invalid_values_without_dispatch(self):
        client = GameExpClient(FakeTransport())
        invalid_id = client.initialize(
            "exp/42",
            request_id="req_invalid_id",
        )
        self.assertEqual(invalid_id["status"], "REJECTED")

        invalid_pr = client.integrate_finalize(
            "EXP-21",
            "0",
            request_id="req_invalid_pr",
        )
        self.assertEqual(invalid_pr["status"], "REJECTED")

        invalid_mode = client.archive(
            "EXP-21",
            "DELETE",
            request_id="req_invalid_archive",
        )
        self.assertEqual(invalid_mode["status"], "REJECTED")

    def test_archive_abort_submits_human_gated_request(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        result = client.archive_abort(
            "EXP-21",
            "A-21-1",
            "cancel before claim",
            actor_claim="reviewer",
            request_id="req_archive_abort_test",
        )
        self.assertEqual(result["status"], "ACCEPTED")
        sent = transport.dispatched[-1]
        self.assertEqual(sent["request_id"], "req_archive_abort_test")
        self.assertIn("payload_b64", sent)

    def _archive_fixture(self, transport, *, mode, branch_sha):
        experiment_id = "EXP-21"
        archive_id = "A-21-1"
        expected = "b" * 40
        transport._ledger_json[f"experiments/{experiment_id}/state.json"] = {
            "kind": "experiment_state",
            "experiment_id": experiment_id,
            "lifecycle": "ARCHIVED",
            "current_archive_id": archive_id,
        }
        transport._ledger_json[
            f"experiments/{experiment_id}/archives/{archive_id}.json"
        ] = {
            "kind": "archive_operation",
            "archive_id": archive_id,
            "experiment_id": experiment_id,
            "phase": "COMMITTED",
            "mode": mode,
            "expected_branch_sha": expected,
            "branch_ref": "refs/heads/exp/21",
            "final_tag_ref": "refs/tags/exp-final/21",
        }
        transport._git_refs["tags/exp-final/21"] = {
            "object": {"type": "tag", "sha": "1" * 40}
        }
        transport._tag_objects["1" * 40] = {
            "object": {"type": "commit", "sha": expected},
            "message": "\n".join(
                [
                    "game-exp archive A-21-1",
                    "",
                    "game-exp-experiment: EXP-21",
                    "game-exp-archive-id: A-21-1",
                    f"game-exp-mode: {mode}",
                    f"game-exp-source-sha: {expected}",
                ]
            ),
        }
        if branch_sha is not None:
            transport._git_refs["heads/exp/21"] = {
                "object": {"type": "commit", "sha": branch_sha}
            }

    def test_archive_health_atomic_delete_passes_with_branch_absent(self):
        transport = FakeTransport()
        self._archive_fixture(transport, mode="ATOMIC_DELETE", branch_sha=None)
        result = GameExpClient(transport).archive_health("EXP-21")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["code"], "ARCHIVE_HEALTHY")

    def test_archive_health_retain_branch_drift_is_warning(self):
        transport = FakeTransport()
        self._archive_fixture(transport, mode="RETAIN_BRANCH", branch_sha="c" * 40)
        result = GameExpClient(transport).archive_health("EXP-21")
        self.assertEqual(result["status"], "WARN")
        self.assertEqual(result["code"], "POST_ARCHIVE_BRANCH_DRIFT")
        self.assertEqual(result["official_snapshot_sha"], "b" * 40)
        self.assertEqual(result["branch_sha"], "c" * 40)

    def test_archive_health_missing_final_tag_is_failure(self):
        transport = FakeTransport()
        self._archive_fixture(transport, mode="ATOMIC_DELETE", branch_sha=None)
        transport._git_refs.pop("tags/exp-final/21")
        result = GameExpClient(transport).archive_health("EXP-21")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["code"], "ARCHIVE_FINAL_TAG_MISSING")

    def test_doctor_surfaces_archive_warning_without_overwriting_snapshot(self):
        transport = FakeTransport()
        self._archive_fixture(transport, mode="RETAIN_BRANCH", branch_sha="c" * 40)
        result = GameExpClient(transport).doctor("EXP-21")
        self.assertEqual(result["status"], "WARN")
        archive = next(row for row in result["checks"] if row["name"] == "archive_health")
        self.assertEqual(archive["status"], "WARN")
        self.assertEqual(archive["detail"]["code"], "POST_ARCHIVE_BRANCH_DRIFT")

    def test_doctor_skips_archive_health_for_unbound_experiment(self):
        result = GameExpClient(FakeTransport()).doctor("EXP-50")
        self.assertEqual(result["status"], "PASS")
        archive = next(row for row in result["checks"] if row["name"] == "archive_health")
        self.assertEqual(archive["status"], "SKIP")
        self.assertEqual(archive["detail"]["code"], "EXPERIMENT_NOT_BOUND")

    def test_doctor_pass(self):
        result = GameExpClient(FakeTransport()).doctor()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(all(row["status"] == "PASS" for row in result["checks"]))


    def test_doctor_classifies_private_free_ruleset_limit_as_fail(self):
        transport = FakeTransport()
        def blocked_rulesets():
            raise ClientError(
                "HTTP 403: Upgrade to GitHub Pro or make this repository public "
                "to enable this feature."
            )
        transport.ruleset_details = blocked_rulesets
        result = GameExpClient(transport).doctor()
        self.assertEqual(result["status"], "FAIL")
        rulesets = next(row for row in result["checks"] if row["name"] == "rulesets")
        self.assertEqual(rulesets["status"], "FAIL")
        self.assertEqual(
            rulesets["detail"]["code"],
            "RULESETS_PLAN_UNSUPPORTED",
        )

    def _execution_claim_record(
        self,
        *,
        action="candidate_build",
        experiment_id="EXP-21",
        arguments=None,
        state=None,
    ):
        state = state or {
            "experiment_id": experiment_id,
            "lifecycle": "REVIEW",
            "sequence": 1,
            "last_decision_id": "req_prev",
            "archive_lock": None,
        }
        payload = {
            "kind": "operation_request",
            "schema_version": 1,
            "operation": "execution.claim",
            "input": {
                "experiment_id": experiment_id,
                "action": action,
                "arguments": arguments or {},
                "state_digest": digest_object(state),
            },
            "preconditions": {},
        }
        return state, {
            "request_id": "req_exec_21",
            "payload": payload,
            "payload_digest": digest_object(payload),
            "domain_status": "REQUEST_ONLY",
            "domain_experiment_id": experiment_id,
            "trusted_actor": {
                "login": "alice",
                "user_id": "1001",
                "permission": "write",
            },
        }

    def test_capabilities_expose_contract_without_treating_access_as_authority(self):
        result = GameExpClient(FakeTransport()).capabilities()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["contract"]["version"], "1.0")
        self.assertEqual(result["contract"]["manifest_schema_versions"], [1, 2, 3])
        self.assertEqual(result["contract"]["recommended_manifest_schema_version"], 2)
        self.assertEqual(result["contract"]["project_policy_schema_versions"], [1, 2, 3])
        self.assertTrue(result["features"]["self_describing_manifest"])
        self.assertTrue(result["features"]["manifest_schema_v2"])
        self.assertTrue(result["features"]["manifest_schema_v3"])
        self.assertTrue(result["features"]["evaluation_evidence_v1"])
        evaluation = result["evaluation_evidence"]
        self.assertEqual(evaluation["protocol_version"], 1)
        self.assertEqual(
            evaluation["screening_states"],
            ["ELIGIBLE", "INELIGIBLE", "INCONCLUSIVE"],
        )
        self.assertFalse(evaluation["screening_changes_lifecycle"])
        self.assertFalse(evaluation["persistent_comparison_set"])
        self.assertEqual(evaluation["small_candidate_ranking"], "PAIRWISE_NO_ELO")
        self.assertTrue(result["features"]["iteration_routing_v1"])
        self.assertTrue(result["features"]["optional_implementation_capabilities_v1"])
        self.assertTrue(result["features"]["collaboration_coordination_v1"])
        self.assertTrue(result["features"]["collaboration_coordination_v2"])
        self.assertTrue(result["features"]["precise_execution_preconditions_v2"])
        self.assertTrue(result["features"]["resumable_work_handoff_v2"])
        coordination = result["collaboration_coordination"]
        self.assertEqual(coordination["protocol_version"], 2)
        self.assertTrue(coordination["intent_before_source_edit"])
        self.assertTrue(coordination["stale_base_rejected"])
        self.assertEqual(coordination["overlap_policy"], "DERIVED_SURFACE_NOT_LOCK")
        self.assertFalse(coordination["persistent_conflict_objects"])
        self.assertTrue(coordination["isolated_workspace_for_overlap"])
        self.assertFalse(coordination["lifecycle_authority"])
        self.assertIn("collaboration_context", result["queries"])
        self.assertIn("work.claim", result["commands"])
        self.assertIn("work.release", result["commands"])
        godot = result["recommended_capabilities"]["godot_prototype_studio"]
        self.assertEqual(godot["id"], "godot-prototype-studio")
        self.assertEqual(
            godot["source_url"],
            "https://github.com/siskosun/godot-prototype-studio",
        )
        self.assertFalse(godot["required"])
        self.assertFalse(godot["missing_is_blocking"])
        self.assertFalse(godot["affects_experiment_health"])
        self.assertEqual(godot["fallback"], "host_native_source_editing")
        routing = result["iteration_routing"]
        self.assertEqual(routing["default_existing_experiment_change"], "REVISION")
        self.assertFalse(routing["clear_revision_requires_confirmation"])
        self.assertTrue(routing["new_experiment_requires_confirmation"])
        self.assertEqual(routing["ambiguous_case"], "ASK_DESIGN_INTENT")
        self.assertTrue(routing["revision"]["reuse_experiment"])
        self.assertTrue(routing["revision"]["reuse_canonical_branch"])
        self.assertFalse(routing["revision"]["new_issue"])
        self.assertFalse(routing["revision"]["new_branch"])
        self.assertTrue(routing["revision"]["new_candidate_after_substantive_change"])
        self.assertFalse(routing["revision"]["previous_review_carries_forward"])
        self.assertFalse(routing["selected_or_terminal_work_reopens_automatically"])
        self.assertTrue(result["features"]["board_presentation_v3"])
        self.assertTrue(result["features"]["board_presentation_v4"])
        self.assertTrue(result["features"]["strict_chinese_board_copy"])
        self.assertTrue(result["features"]["natural_chinese_board"])
        self.assertIn("experiment_template", result["queries"])
        self.assertTrue(result["recovery"]["cross_interface"])
        self.assertFalse(result["access_snapshot_authoritative_for_execution"])

    def test_collaboration_context_detects_sync_and_nonblocking_overlap(self):
        transport = FakeTransport()
        transport._ledger_json["experiments/EXP-7/state.json"] = {
            "kind": "experiment_state",
            "experiment_id": "EXP-7",
            "lifecycle": "ACTIVE",
            "active_work_claim_ids": ["req_work_1", "req_work_2"],
        }
        transport._ledger_json["experiments/EXP-7/binding.json"] = {
            "initialization": {"branch_ref": "refs/heads/exp/7"},
        }
        transport._ledger_json["experiments/EXP-7/manifest.json"] = {
            "title": "Movement tuning",
            "hypothesis": "Movement feel improves retention in playtest.",
            "success_criteria": ["Players describe movement as responsive."],
            "kill_criteria": ["Players still describe movement as sluggish."],
        }
        transport._ledger_json[
            "experiments/EXP-7/work-claims/req_work_1.json"
        ] = {
            "kind": "work_claim",
            "claim_id": "req_work_1",
            "experiment_id": "EXP-7",
            "base_source_sha": "b" * 40,
            "summary": "Tune movement",
            "paths": ["games/player"],
            "actor": {"login": "alice"},
            "executor": {"harness": "codex", "agent": "gpt"},
        }
        transport._ledger_json[
            "experiments/EXP-7/work-claims/req_work_2.json"
        ] = {
            "kind": "work_claim",
            "claim_id": "req_work_2",
            "experiment_id": "EXP-7",
            "base_source_sha": "b" * 40,
            "summary": "Adjust movement input",
            "paths": ["games/player/input"],
            "actor": {"login": "bob"},
            "executor": {"harness": "qoder", "agent": "qoder-agent"},
        }
        transport._git_refs["heads/exp/7"] = {
            "object": {"type": "commit", "sha": "b" * 40}
        }

        result = GameExpClient(transport).collaboration_context(
            "EXP-7",
            observed_source_sha="b" * 40,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["sync_status"], "CURRENT")
        self.assertEqual(result["next_action"], "REVIEW_OVERLAP")
        self.assertTrue(result["coordination_required"])
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertFalse(result["conflicts"][0]["blocking"])
        self.assertEqual(
            result["conflicts"][0]["claim_ids"],
            ["req_work_1", "req_work_2"],
        )

        transport._compare_commits[("b" * 40, "c" * 40)] = {"status": "behind"}
        stale_observer = GameExpClient(transport).collaboration_context(
            "EXP-7",
            observed_source_sha="c" * 40,
        )
        self.assertEqual(stale_observer["sync_status"], "STALE")
        self.assertEqual(stale_observer["next_action"], "SYNC_SOURCE")

        transport._compare_commits[("b" * 40, "e" * 40)] = {"status": "ahead"}
        local_ahead = GameExpClient(transport).collaboration_context(
            "EXP-7",
            observed_source_sha="e" * 40,
        )
        self.assertEqual(local_ahead["freshness"]["source"]["status"], "CURRENT")
        self.assertEqual(local_ahead["freshness"]["source"]["reason"], "LOCAL_AHEAD")

        transport._git_refs["heads/exp/7"] = {
            "object": {"type": "commit", "sha": "d" * 40}
        }
        advanced = GameExpClient(transport).collaboration_context("EXP-7")
        self.assertEqual(len(advanced["active_claims"]), 2)
        self.assertEqual(len(advanced["stale_claims"]), 2)
        self.assertTrue(advanced["coordination_required"])
        self.assertTrue(
            all(row["lease_status"] == "UNKNOWN" for row in advanced["claims"])
        )
        self.assertTrue(
            all(
                row["freshness"]["reason"] == "SOURCE_ADVANCED"
                for row in advanced["stale_claims"]
            )
        )

    def test_work_claim_and_release_use_protected_operations(self):
        transport = FakeTransport()
        client = GameExpClient(transport)
        claim = client.work_claim(
            "EXP-7",
            base_source_sha="b" * 40,
            summary="Tune movement",
            paths=["games/player"],
            harness="codex",
            agent="gpt",
            session_id="s1",
            request_id="req_work_claim_7",
        )
        self.assertEqual(claim["status"], "ACCEPTED")
        payload = transport.dispatched[-1]
        self.assertEqual(payload["request_id"], "req_work_claim_7")
        release = client.work_release(
            "EXP-7",
            claim_id="req_work_claim_7",
            outcome="ABANDONED",
            notes="Superseded by another implementation.",
            request_id="req_work_release_7",
        )
        self.assertEqual(release["status"], "ACCEPTED")
        self.assertEqual(transport.dispatched[-1]["request_id"], "req_work_release_7")

    def test_async_mutation_requires_stable_request_id(self):
        result = GameExpClient(FakeTransport()).candidate("EXP-21")
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn("stable request_id", result["error"])

    def test_operation_get_resolves_committed_execution_claim_without_resubmitting(self):
        transport = FakeTransport()
        state, record = self._execution_claim_record()
        transport.records["req_exec_21"] = record
        result = GameExpClient(transport).operation_get("req_exec_21")
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(result["operation_status"], "CLAIMED")
        self.assertTrue(result["safe_to_resume"])
        self.assertEqual(transport.dispatched, [])

    def test_resume_execution_dispatches_same_claim_id_once(self):
        transport = FakeTransport()
        state, record = self._execution_claim_record()
        transport.records["req_exec_21"] = record
        transport._ledger_json["experiments/EXP-21/state.json"] = state
        result = GameExpClient(transport).resume_execution("req_exec_21")
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertEqual(result["operation_status"], "DISPATCHED")
        self.assertEqual(
            transport.dispatched[-1],
            {
                "execution": "candidate_build",
                "experiment_id": "EXP-21",
                "request_id": "req_exec_21",
                "arguments": {},
            },
        )

    def test_resume_execution_rejects_state_drift_instead_of_redispatching(self):
        transport = FakeTransport()
        state, record = self._execution_claim_record()
        transport.records["req_exec_21"] = record
        changed = dict(state)
        changed["sequence"] = 2
        transport._ledger_json["experiments/EXP-21/state.json"] = changed
        result = GameExpClient(transport).resume_execution("req_exec_21")
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(
            result["conflict_type"],
            "EXECUTION_PRECONDITION_CHANGED",
        )
        self.assertEqual(transport.dispatched, [])

    def test_same_operation_id_with_different_async_claim_is_conflict(self):
        transport = FakeTransport()
        _state, record = self._execution_claim_record()
        transport.records["req_exec_21"] = record
        result = GameExpClient(transport).start_execution(
            action="rehearse",
            experiment_id="EXP-21",
            request_id="req_exec_21",
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["conflict_type"], "REQUEST_ID_CONFLICT")

    def test_operation_get_reports_completed_worker_result(self):
        transport = FakeTransport()
        state, record = self._execution_claim_record()
        transport.records["req_exec_21"] = record
        transport.execution_runs[("candidate_build", "req_exec_21")] = {
            "databaseId": 900,
            "displayTitle": "game-exp:candidate_build:req_exec_21",
            "status": "completed",
            "conclusion": "success",
            "url": "https://github.com/owner/repo/actions/runs/900",
        }
        transport._ledger_json["experiments/EXP-21/state.json"] = state
        result = GameExpClient(transport).operation_get("req_exec_21")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["operation_status"], "SUCCEEDED")

    def test_notification_cursor_scope_and_incremental_resume(self):
        client = GameExpClient(FakeTransport())
        checkpoint = client._encode_notification_cursor(
            {
                "v": 1,
                "kind": "checkpoint",
                "snapshot": "a" * 40,
                "viewer_login": "bob",
                "subject_id": "arena-duel",
            }
        )
        new_board = {"status": "PASS", "snapshot_head": "b" * 40}
        old_board = {"status": "PASS", "snapshot_head": "a" * 40}
        old_event = {
            "event_id": "EXP-1:EXPERIMENT_CREATED:EXP-1",
            "experiment_id": "EXP-1",
            "occurred_at": "2026-09-26T00:00:00Z",
            "_order": 0,
        }
        new_event = {
            "event_id": "EXP-2:EXPERIMENT_CREATED:EXP-2",
            "experiment_id": "EXP-2",
            "occurred_at": "2026-09-27T00:00:00Z",
            "_order": 0,
        }
        with (
            patch.object(client, "board", side_effect=[new_board, old_board]),
            patch.object(
                client,
                "_notification_rows",
                side_effect=[[old_event, new_event], [old_event]],
            ),
        ):
            result = client.notification_feed(
                viewer_login="bob",
                subject_id="arena-duel",
                after=checkpoint,
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(
            [row["event_id"] for row in result["notifications"]],
            ["EXP-2:EXPERIMENT_CREATED:EXP-2"],
        )
        self.assertTrue(result["checkpoint_ready"])
        self.assertIsNotNone(result["checkpoint_cursor"])

        mismatch = client.notification_feed(
            viewer_login="bob",
            subject_id="other",
            after=checkpoint,
        )
        self.assertEqual(mismatch["code"], "CURSOR_SCOPE_MISMATCH")

    def test_notification_feed_rejects_invalid_limit(self):
        result = GameExpClient(FakeTransport()).notification_feed(limit=0)
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["reason"], "invalid_limit")

    def test_prototype_handoff_rejects_invalid_experiment_id(self):
        result = GameExpClient(FakeTransport()).prototype_handoff("bad")
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["reason"], "invalid_experiment_id")


if __name__ == "__main__":
    unittest.main()
