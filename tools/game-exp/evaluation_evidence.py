from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import pathlib
import re
import tarfile
from typing import Any

from protocol_core import canonical_json_bytes, digest_object

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
EVIDENCE_SOURCE = "TRUSTED_OBSERVED"
SCREENING = {"ELIGIBLE", "INELIGIBLE", "INCONCLUSIVE"}
RESULT_STATUSES = {"PASS", "FAIL_PRODUCT_DEFECT", "INCONCLUSIVE"}
CLASSIFICATIONS = {
    "NONE",
    "PRODUCT_DEFECT",
    "TEST_HARNESS",
    "ENVIRONMENT",
    "DESIGN_RISK",
    "INCONCLUSIVE",
}
SEED_POLICIES = {"FIXED", "DECLARED", "NOT_APPLICABLE"}
REPLAY_POLICIES = {"REQUIRED", "OPTIONAL", "NOT_APPLICABLE"}
SNAPSHOT_POLICIES = {"REQUIRED", "OPTIONAL", "NOT_APPLICABLE"}


class EvaluationEvidenceError(ValueError):
    pass


def _strict_keys(
    value: dict[str, Any],
    required: set[str],
    where: str,
    *,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing or extra:
        raise EvaluationEvidenceError(
            f"{where}: keys mismatch; missing={sorted(missing)} extra={sorted(extra)}"
        )


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationEvidenceError(f"{where}: expected non-empty string")
    return value


def _safe_rel_path(value: Any, where: str) -> str:
    value = _string(value, where)
    if (
        value.startswith("/")
        or value.startswith("~")
        or "\\" in value
        or "//" in value
        or any(part in {"", ".", ".."} for part in pathlib.PurePosixPath(value).parts)
    ):
        raise EvaluationEvidenceError(f"{where}: expected safe normalized relative path")
    return value.rstrip("/")


def _requirement(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationEvidenceError(f"{where}: expected object")
    _strict_keys(value, {"id", "goal", "required"}, where)
    rid = _string(value["id"], f"{where}.id")
    if not ID_RE.fullmatch(rid):
        raise EvaluationEvidenceError(f"{where}.id: expected lowercase stable id")
    goal = _string(value["goal"], f"{where}.goal")
    if not isinstance(value["required"], bool):
        raise EvaluationEvidenceError(f"{where}.required: expected boolean")
    return {"id": rid, "goal": goal, "required": value["required"]}


def validate_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationEvidenceError("profile: expected object")
    _strict_keys(
        value,
        {
            "schema_version",
            "profile_id",
            "standing_requirements",
            "hypothesis_requirements",
            "interface",
        },
        "profile",
    )
    if value["schema_version"] != 1:
        raise EvaluationEvidenceError("profile.schema_version must equal 1")
    profile_id = _string(value["profile_id"], "profile.profile_id")
    if not ID_RE.fullmatch(profile_id):
        raise EvaluationEvidenceError("profile.profile_id must be a lowercase stable id")

    groups: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    for field in ("standing_requirements", "hypothesis_requirements"):
        rows = value[field]
        if not isinstance(rows, list):
            raise EvaluationEvidenceError(f"profile.{field}: expected array")
        normalized: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            item = _requirement(row, f"profile.{field}[{index}]")
            if item["id"] in seen:
                raise EvaluationEvidenceError(
                    f"profile requirement id duplicated: {item['id']}"
                )
            seen.add(item["id"])
            normalized.append(item)
        groups[field] = normalized

    if not groups["standing_requirements"]:
        raise EvaluationEvidenceError("profile requires at least one standing requirement")
    if not any(
        item["required"]
        for item in groups["standing_requirements"] + groups["hypothesis_requirements"]
    ):
        raise EvaluationEvidenceError("profile requires at least one required requirement")

    interface = value["interface"]
    if not isinstance(interface, dict):
        raise EvaluationEvidenceError("profile.interface: expected object")
    _strict_keys(
        interface,
        {
            "scenario_id",
            "player_goal",
            "seed_policy",
            "replay_policy",
            "snapshot_policy",
        },
        "profile.interface",
    )
    scenario_id = _string(interface["scenario_id"], "profile.interface.scenario_id")
    player_goal = _string(interface["player_goal"], "profile.interface.player_goal")
    if interface["seed_policy"] not in SEED_POLICIES:
        raise EvaluationEvidenceError("profile.interface.seed_policy is invalid")
    if interface["replay_policy"] not in REPLAY_POLICIES:
        raise EvaluationEvidenceError("profile.interface.replay_policy is invalid")
    if interface["snapshot_policy"] not in SNAPSHOT_POLICIES:
        raise EvaluationEvidenceError("profile.interface.snapshot_policy is invalid")

    return {
        "schema_version": 1,
        "profile_id": profile_id,
        **groups,
        "interface": {
            "scenario_id": scenario_id,
            "player_goal": player_goal,
            "seed_policy": interface["seed_policy"],
            "replay_policy": interface["replay_policy"],
            "snapshot_policy": interface["snapshot_policy"],
        },
    }


def evaluation_profile_digest(value: Any) -> str:
    return digest_object(validate_profile(json.loads(json.dumps(value))))


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: pathlib.Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _required_ids(profile: dict[str, Any]) -> set[str]:
    return {
        item["id"]
        for field in ("standing_requirements", "hypothesis_requirements")
        for item in profile[field]
        if item["required"]
    }


def validate_result(
    profile: dict[str, Any],
    value: Any,
    *,
    source_sha: str,
    evidence_root: pathlib.Path,
) -> dict[str, Any]:
    profile = validate_profile(json.loads(json.dumps(profile)))
    if not isinstance(value, dict):
        raise EvaluationEvidenceError("result: expected object")
    _strict_keys(
        value,
        {
            "schema_version",
            "profile_digest",
            "source_sha",
            "run_mode",
            "trace_digest",
            "step_mode",
            "requirements",
        },
        "result",
    )
    if value["schema_version"] != 1:
        raise EvaluationEvidenceError("result.schema_version must equal 1")
    expected_profile_digest = evaluation_profile_digest(profile)
    if value["profile_digest"] != expected_profile_digest:
        raise EvaluationEvidenceError("result.profile_digest mismatch")
    if value["source_sha"] != source_sha or not SHA_RE.fullmatch(source_sha):
        raise EvaluationEvidenceError("result.source_sha mismatch")
    if value["run_mode"] not in {"TRUSTED_REPLAY", "TRUSTED_CHECK"}:
        raise EvaluationEvidenceError("result.run_mode must be TRUSTED_REPLAY or TRUSTED_CHECK")
    trace_digest = value["trace_digest"]
    if trace_digest is not None and (
        not isinstance(trace_digest, str) or not SHA256_RE.fullmatch(trace_digest)
    ):
        raise EvaluationEvidenceError("result.trace_digest must be sha256 digest or null")
    if value["step_mode"] not in {
        "SCENE_CONTROLLED",
        "REALTIME_PHYSICS_WAIT",
        "NOT_APPLICABLE",
    }:
        raise EvaluationEvidenceError("result.step_mode is invalid")

    rows = value["requirements"]
    if not isinstance(rows, list):
        raise EvaluationEvidenceError("result.requirements must be an array")
    profile_ids = {
        item["id"]
        for field in ("standing_requirements", "hypothesis_requirements")
        for item in profile[field]
    }
    seen: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        where = f"result.requirements[{index}]"
        if not isinstance(row, dict):
            raise EvaluationEvidenceError(f"{where}: expected object")
        _strict_keys(
            row,
            {"id", "status", "classification", "evidence"},
            where,
        )
        rid = _string(row["id"], f"{where}.id")
        if rid not in profile_ids:
            raise EvaluationEvidenceError(f"{where}.id not declared in profile")
        if rid in seen:
            raise EvaluationEvidenceError(f"{where}.id duplicated")
        seen.add(rid)
        status = row["status"]
        classification = row["classification"]
        if status not in RESULT_STATUSES:
            raise EvaluationEvidenceError(f"{where}.status invalid")
        if classification not in CLASSIFICATIONS:
            raise EvaluationEvidenceError(f"{where}.classification invalid")
        if status == "FAIL_PRODUCT_DEFECT" and classification != "PRODUCT_DEFECT":
            raise EvaluationEvidenceError(
                f"{where}: FAIL_PRODUCT_DEFECT requires PRODUCT_DEFECT classification"
            )
        if status == "PASS" and classification != "NONE":
            raise EvaluationEvidenceError(f"{where}: PASS requires NONE classification")
        if status == "INCONCLUSIVE" and classification == "PRODUCT_DEFECT":
            raise EvaluationEvidenceError(
                f"{where}: INCONCLUSIVE cannot claim PRODUCT_DEFECT"
            )

        evidence = row["evidence"]
        if not isinstance(evidence, list):
            raise EvaluationEvidenceError(f"{where}.evidence must be an array")
        normalized_evidence: list[dict[str, str]] = []
        for eindex, evidence_item in enumerate(evidence):
            ewhere = f"{where}.evidence[{eindex}]"
            if not isinstance(evidence_item, dict):
                raise EvaluationEvidenceError(f"{ewhere}: expected object")
            _strict_keys(evidence_item, {"path", "digest"}, ewhere)
            rel = _safe_rel_path(evidence_item["path"], f"{ewhere}.path")
            digest = evidence_item["digest"]
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                raise EvaluationEvidenceError(f"{ewhere}.digest invalid")
            target = (evidence_root / rel).resolve()
            root = evidence_root.resolve()
            if root != target and root not in target.parents:
                raise EvaluationEvidenceError(f"{ewhere}.path escapes evidence root")
            if not target.is_file():
                raise EvaluationEvidenceError(f"{ewhere}.path missing: {rel}")
            actual = _sha256_file(target)
            if actual != digest:
                raise EvaluationEvidenceError(
                    f"{ewhere}.digest mismatch expected={digest} actual={actual}"
                )
            normalized_evidence.append({"path": rel, "digest": digest})
        normalized_rows.append(
            {
                "id": rid,
                "status": status,
                "classification": classification,
                "evidence": normalized_evidence,
            }
        )

    required = _required_ids(profile)
    missing_required = required - seen
    if missing_required:
        raise EvaluationEvidenceError(
            f"result missing required requirement ids: {sorted(missing_required)}"
        )

    by_id = {row["id"]: row for row in normalized_rows}
    required_rows = [by_id[rid] for rid in sorted(required)]
    if any(row["status"] == "FAIL_PRODUCT_DEFECT" for row in required_rows):
        screening = "INELIGIBLE"
    elif any(row["status"] != "PASS" for row in required_rows):
        screening = "INCONCLUSIVE"
    else:
        screening = "ELIGIBLE"

    normalized = {
        "schema_version": 1,
        "profile_digest": expected_profile_digest,
        "source_sha": source_sha,
        "run_mode": value["run_mode"],
        "trace_digest": trace_digest,
        "step_mode": value["step_mode"],
        "requirements": normalized_rows,
    }
    return {
        "result": normalized,
        "result_digest": digest_object(normalized),
        "screening": screening,
        "source": EVIDENCE_SOURCE,
        "required_requirement_ids": sorted(required),
    }


def _safe_extract(bundle: pathlib.Path, destination: pathlib.Path) -> None:
    with tarfile.open(bundle, "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            if not member.isfile():
                raise EvaluationEvidenceError(
                    f"evaluation bundle contains non-file entry: {member.name}"
                )
            rel = _safe_rel_path(member.name, "evaluation bundle member")
            target = (destination / rel).resolve()
            root = destination.resolve()
            if root not in target.parents:
                raise EvaluationEvidenceError("evaluation bundle member escapes destination")
        tf.extractall(destination)


def package_output(output_dir: pathlib.Path, bundle: pathlib.Path) -> None:
    if not output_dir.is_dir():
        raise EvaluationEvidenceError("evaluation output directory is missing")
    files = sorted(path for path in output_dir.rglob("*") if path.is_file())
    if not files:
        raise EvaluationEvidenceError("evaluation output directory is empty")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for path in files:
            arcname = path.relative_to(output_dir).as_posix()
            _safe_rel_path(arcname, "evaluation output path")
            info = tf.gettarinfo(str(path), arcname=arcname)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            with path.open("rb") as fh:
                tf.addfile(info, fh)
    with bundle.open("wb") as raw_fh:
        with gzip.GzipFile(fileobj=raw_fh, mode="wb", filename="", mtime=0) as gz:
            gz.write(raw.getvalue())


def observe_bundle(
    *,
    profile_path: pathlib.Path,
    bundle_path: pathlib.Path,
    source_sha: str,
    expected_profile_digest: str,
    work_dir: pathlib.Path,
) -> dict[str, Any]:
    profile = validate_profile(_load_json(profile_path))
    actual_profile_digest = evaluation_profile_digest(profile)
    if actual_profile_digest != expected_profile_digest:
        raise EvaluationEvidenceError(
            "evaluation profile digest differs from Manifest reference"
        )
    extract_dir = work_dir / "evaluation-extracted"
    extract_dir.mkdir(parents=True, exist_ok=False)
    _safe_extract(bundle_path, extract_dir)
    result_path = extract_dir / "result.json"
    if not result_path.is_file():
        raise EvaluationEvidenceError("evaluation bundle must contain result.json")
    summary = validate_result(
        profile,
        _load_json(result_path),
        source_sha=source_sha,
        evidence_root=extract_dir,
    )
    summary["enabled"] = True
    summary["profile_id"] = profile["profile_id"]
    summary["profile_digest"] = actual_profile_digest
    summary["bundle_digest"] = _sha256_file(bundle_path)
    summary["bundle_asset_name"] = "evaluation-output.tgz"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate game-exp evaluation profiles and trusted evaluation bundles.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("profile")
    p.add_argument("profile")
    p.add_argument("--expected-digest")

    package = sub.add_parser("package")
    package.add_argument("output_dir")
    package.add_argument("bundle")

    observe = sub.add_parser("observe")
    observe.add_argument("profile")
    observe.add_argument("bundle")
    observe.add_argument("--source-sha", required=True)
    observe.add_argument("--expected-profile-digest", required=True)
    observe.add_argument("--work-dir", required=True)
    observe.add_argument("--summary-out", required=True)

    args = parser.parse_args()
    if args.command == "profile":
        value = validate_profile(_load_json(pathlib.Path(args.profile)))
        digest = evaluation_profile_digest(value)
        if args.expected_digest and digest != args.expected_digest:
            raise EvaluationEvidenceError("profile digest mismatch")
        print(json.dumps({"valid": True, "profile_digest": digest}, sort_keys=True))
        return 0
    if args.command == "package":
        package_output(pathlib.Path(args.output_dir), pathlib.Path(args.bundle))
        return 0

    summary = observe_bundle(
        profile_path=pathlib.Path(args.profile),
        bundle_path=pathlib.Path(args.bundle),
        source_sha=args.source_sha,
        expected_profile_digest=args.expected_profile_digest,
        work_dir=pathlib.Path(args.work_dir),
    )
    pathlib.Path(args.summary_out).write_bytes(canonical_json_bytes(summary) + b"\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
