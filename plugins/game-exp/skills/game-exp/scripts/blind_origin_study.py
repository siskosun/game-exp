"""Optional, local, non-authoritative blinded AI-only vs human-AI playtest.

This sidecar never writes a protected game-exp Ledger, Review or decision.
Candidate/Evaluation fields are operator supplied and must be reconciled with
an immutable trusted Candidate before any real study.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import pathlib
import re
import secrets
import sys
from typing import Any
from urllib.parse import unquote, urlsplit


ROOT = pathlib.Path(__file__).resolve()
TOOLS = ROOT.parents[5] / "tools" / "game-exp"
if TOOLS.is_dir():
    sys.path.insert(0, str(TOOLS))
try:
    from protocol_core import digest_object
except ImportError:  # Standalone script in the installed Skill
    def digest_object(value: Any) -> str:
        """Canonical hash for this sidecar; no trusted Ledger authority."""
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()


DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
CHOICES = (
    "A_MUCH_BETTER", "A_SLIGHTLY_BETTER", "NO_CLEAR_DIFFERENCE",
    "B_SLIGHTLY_BETTER", "B_MUCH_BETTER", "INCONCLUSIVE",
)


class StudyError(ValueError):
    pass


def keys(obj: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict) or set(obj) != expected:
        raise StudyError(f"{where}: expected keys {sorted(expected)}")
    return obj


def ident(value: Any, where: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise StudyError(f"{where}: invalid identifier")
    return value


def digest(value: Any, where: str) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise StudyError(f"{where}: invalid sha256 digest")
    return value


def positive(value: Any, where: str, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise StudyError(f"{where}: expected positive integer")
    return value


def label(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise StudyError(f"{where}: required nonempty text, max 500 characters")
    return value


def https_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise StudyError("delivery_url: invalid URL")
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.fragment or any(ord(c) < 32 for c in value)):
        raise StudyError("delivery_url: require shareable https URL without credentials/fragment")
    # Decode a bounded number of times: percent-encoding must not hide
    # recognizable producer labels from the participant-facing URL.
    origin_clue = re.compile(r"ai[-_]only|human[-_]ai|human[-_]made|human[-_]design", re.I)
    decoded = value
    for _ in range(5):
        if origin_clue.search(decoded):
            raise StudyError("delivery_url: producer-origin clue; publish neutral playable URL")
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return value


def validate_plan(plan: Any) -> dict[str, Any]:
    keys(plan, {"schema_version", "study_id", "brief_digest", "baseline_digest",
                "evaluation_profile_digest", "resource_budget", "playtest", "variants"}, "plan")
    if plan["schema_version"] != 1:
        raise StudyError("schema_version must be 1")
    ident(plan["study_id"], "study_id")
    for field in ("brief_digest", "baseline_digest", "evaluation_profile_digest"):
        digest(plan[field], field)
    budget = keys(plan["resource_budget"], {"model", "max_minutes", "max_model_calls"}, "resource_budget")
    label(budget["model"], "resource_budget.model")
    positive(budget["max_minutes"], "max_minutes")
    positive(budget["max_model_calls"], "max_model_calls")
    test = keys(plan["playtest"], {"minimum_seconds_per_version", "planned_min_responses",
                                  "population", "recruitment", "limitations"}, "playtest")
    positive(test["minimum_seconds_per_version"], "minimum_seconds_per_version")
    positive(test["planned_min_responses"], "planned_min_responses")
    for field in ("population", "recruitment", "limitations"):
        label(test[field], field)
    variants = plan["variants"]
    if not isinstance(variants, list) or len(variants) != 2:
        raise StudyError("plan requires exactly two variants")
    if {v.get("origin") for v in variants if isinstance(v, dict)} != {"AI_ONLY", "HUMAN_AI"}:
        raise StudyError("requires exactly AI_ONLY and HUMAN_AI provenance declarations")
    seen_ids: set[str] = set()
    seen_artifacts: set[str] = set()
    seen_urls: set[str] = set()
    for i, var in enumerate(variants):
        where = f"variants[{i}]"
        keys(var, {"origin", "candidate_id", "source_sha", "artifact_digest",
                   "baseline_digest", "design_trace_digest", "evaluation", "delivery_url", "usage"}, where)
        ident(var["candidate_id"], f"{where}.candidate_id")
        if not isinstance(var["source_sha"], str) or not SHA.fullmatch(var["source_sha"]):
            raise StudyError(f"{where}.source_sha: invalid commit sha")
        for field in ("artifact_digest", "baseline_digest", "design_trace_digest"):
            digest(var[field], f"{where}.{field}")
        if var["baseline_digest"] != plan["baseline_digest"]:
            raise StudyError(f"{where}: baseline differs from shared plan")
        ev = keys(var["evaluation"], {"profile_digest", "result_digest", "screening", "source"}, f"{where}.evaluation")
        digest(ev["profile_digest"], "evaluation.profile_digest")
        digest(ev["result_digest"], "evaluation.result_digest")
        if (ev["profile_digest"] != plan["evaluation_profile_digest"]
                or ev["screening"] != "ELIGIBLE" or ev["source"] != "TRUSTED_OBSERVED"):
            raise StudyError(f"{where}: same eligible Evaluation Profile required (operator claim only)")
        var["delivery_url"] = https_url(var["delivery_url"])
        usage = keys(var["usage"], {"model", "minutes", "model_calls"}, f"{where}.usage")
        if usage["model"] != budget["model"]:
            raise StudyError(f"{where}: production model differs")
        positive(usage["minutes"], "usage.minutes")
        positive(usage["model_calls"], "usage.model_calls")
        if usage["minutes"] > budget["max_minutes"] or usage["model_calls"] > budget["max_model_calls"]:
            raise StudyError(f"{where}: exceeds shared production resource budget")
        if var["candidate_id"] in seen_ids or var["artifact_digest"] in seen_artifacts or var["delivery_url"] in seen_urls:
            raise StudyError("different Candidate, artifact and playable URL required")
        seen_ids.add(var["candidate_id"])
        seen_artifacts.add(var["artifact_digest"])
        seen_urls.add(var["delivery_url"])
    return plan


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _read(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def public_html(study_id: str, session_id: str, urls: list[str], seconds: int) -> str:
    """The exported page contains no design origin, Candidate, or evaluation identifiers."""
    sections = "\n".join(
        f'<section id="version-{slot}"{" hidden" if slot == "B" else ""}><h2>版本 {slot}</h2><p><a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">单独打开版本 {slot}</a></p>'
        f'<iframe title="版本 {slot}" loading="lazy" referrerpolicy="no-referrer" src="{html.escape(url, quote=True)}"></iframe></section>'
        for slot, url in zip(("A", "B"), urls)
    )
    option_lines = "\n".join(
        f'<label><input type="radio" name="choice" value="{choice}">{label_text}</label>'
        for choice, label_text in (
            ("A_MUCH_BETTER", "A 明显更好"), ("A_SLIGHTLY_BETTER", "A 略好"),
            ("NO_CLEAR_DIFFERENCE", "没有明显区别"), ("B_SLIGHTLY_BETTER", "B 略好"),
            ("B_MUCH_BETTER", "B 明显更好"), ("INCONCLUSIVE", "无法判断"),
        )
    )
    payload = json.dumps({"schema_version": 1, "study_id": study_id, "session_id": session_id}, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e")
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>匿名双版本试玩</title><style>
body{{font:16px system-ui,sans-serif;max-width:1100px;margin:20px auto;padding:0 16px;line-height:1.55}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}}
section{{border:1px solid #bbb;border-radius:10px;padding:12px}}
iframe{{width:100%;height:390px;border:1px solid #ddd}}
[hidden]{{display:none!important}}label{{display:block;margin:9px 0}}button{{padding:10px 18px}}
</style></head><body><h1>匿名 A/B 试玩</h1>
<p>请分别试玩两个版本至少 {seconds} 秒。可用框内操作；若无法嵌入，请打开对应链接。
仅评价作品本身；不要猜测制作来源。游戏页面自身可能泄漏来源，主持人须预先核查。</p>
<main>{sections}</main><p><button type="button" id="next-version">已体验 A，继续版本 B</button></p>
<form id="vote" hidden><h2>您的偏好</h2>{option_lines}
<label><input type="checkbox" id="played">我已分别试玩两个版本（自报，系统无法核实）</label>
<button type="submit">下载匿名评价 JSON</button></form>
<p id="message" role="status"></p><script>
const base={payload};
document.getElementById('next-version').addEventListener('click', ()=>{{
 document.getElementById('version-A').hidden=true;
 document.getElementById('version-B').hidden=false;
 document.getElementById('vote').hidden=false;
 document.getElementById('next-version').hidden=true;
}});
document.getElementById('vote').addEventListener('submit', e=>{{
 e.preventDefault();const choice=document.querySelector('input[name="choice"]:checked');
 const played=document.getElementById('played').checked;
 if(!choice || (!played && choice.value!=='INCONCLUSIVE')){{document.getElementById('message').textContent='请先选择结果；有效偏好还需确认试玩过两个版本。';return;}}
 const result={{...base,choice:choice.value,self_reported_played_both:played}};
 const blob=new Blob([JSON.stringify(result,null,2)+'\\n'],{{type:'application/json'}});
 const link=document.createElement('a');link.href=URL.createObjectURL(blob);
 link.download='vote-'+base.session_id+'.json';link.click();URL.revokeObjectURL(link.href);
 document.getElementById('message').textContent='请将下载文件交给实验主持人。页面不会自动上传数据。';
}});
</script></body></html>'''


def prepare(plan_path: pathlib.Path, private_dir: pathlib.Path, public_dir: pathlib.Path, n: int) -> dict[str, Any]:
    positive(n, "sessions")
    if n > 2000:
        raise StudyError("sessions limited to 2000")
    plan = validate_plan(_read(plan_path))
    private_dir, public_dir = private_dir.resolve(), public_dir.resolve()
    if (private_dir == public_dir or private_dir in public_dir.parents or public_dir in private_dir.parents):
        raise StudyError("public and private directories must be disjoint")
    if private_dir.exists() or public_dir.exists():
        raise StudyError("output directories must not already exist")
    private_dir.mkdir(parents=True)
    public_dir.mkdir(parents=True)
    (private_dir / "responses").mkdir()
    try:
        private_dir.chmod(0o700)
    except OSError:
        pass
    indices = [0, 1] * (n // 2) + ([secrets.randbelow(2)] if n % 2 else [])
    secrets.SystemRandom().shuffle(indices)
    sessions = {}
    for first in indices:
        sid = secrets.token_hex(16)
        while sid in sessions:
            sid = secrets.token_hex(16)
        order = [first, 1 - first]
        page = public_html(plan["study_id"], sid,
                           [plan["variants"][j]["delivery_url"] for j in order],
                           plan["playtest"]["minimum_seconds_per_version"])
        name = f"play-{sid}.html"
        raw = page.encode("utf-8")
        (public_dir / name).write_bytes(raw)
        sessions[sid] = {"order": order, "public_file": name, "public_digest": _file_digest(raw)}
    state = {"schema_version": 1, "plan": plan, "plan_digest": digest_object(plan),
             "sessions": sessions, "assignment_set_digest": digest_object(sessions)}
    (private_dir / "trial.json").write_bytes(_json_bytes(state))
    try:
        (private_dir / "trial.json").chmod(0o600)
    except OSError:
        pass
    return {"status": "PREPARED_NO_RESPONSES", "study_id": plan["study_id"],
            "plan_digest": state["plan_digest"], "sessions": n,
            "private_dir": str(private_dir), "public_dir": str(public_dir),
            "evidence_authority": "OPERATOR_SUPPLIED_NOT_TRUSTED"}


def _state(private_dir: pathlib.Path) -> dict[str, Any]:
    state = _read(private_dir / "trial.json")
    keys(state, {"schema_version", "plan", "plan_digest", "sessions", "assignment_set_digest"}, "trial")
    validate_plan(state["plan"])
    if state["schema_version"] != 1 or digest_object(state["plan"]) != state["plan_digest"]:
        raise StudyError("trial plan digest mismatch")
    if digest_object(state["sessions"]) != state["assignment_set_digest"]:
        raise StudyError("trial assignment set digest mismatch")
    return state


def validate_response(value: Any, state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    keys(value, {"schema_version", "study_id", "session_id", "choice", "self_reported_played_both"}, "response")
    if value["schema_version"] != 1 or value["study_id"] != state["plan"]["study_id"]:
        raise StudyError("response study mismatch")
    sid = value["session_id"]
    if not isinstance(sid, str) or sid not in state["sessions"]:
        raise StudyError("response: session was not allocated")
    if value["choice"] not in CHOICES or type(value["self_reported_played_both"]) is not bool:
        raise StudyError("response: invalid choice or played flag")
    if not value["self_reported_played_both"] and value["choice"] != "INCONCLUSIVE":
        raise StudyError("response: preference requires self-reported play of both versions")
    return sid, value


def record(private_dir: pathlib.Path, response_path: pathlib.Path) -> dict[str, Any]:
    state = _state(private_dir)
    sid, response = validate_response(_read(response_path), state)
    row = {"schema_version": 1, "plan_digest": state["plan_digest"],
           "public_digest": state["sessions"][sid]["public_digest"],
           "response": response, "evidence_source": "PARTICIPANT_REPORTED_UNVERIFIED"}
    output = private_dir / "responses" / (sid + ".json")
    with output.open("x", encoding="utf-8") as fh:
        json.dump(row, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    return {"status": "RECORDED_UNVERIFIED", "session_id": sid,
            "record_digest": _file_digest(output.read_bytes())}


def report(private_dir: pathlib.Path, public_dir: pathlib.Path | None = None) -> dict[str, Any]:
    state = _state(private_dir)
    pages_verified = public_dir is not None
    if public_dir is not None:
        for session in state["sessions"].values():
            path = public_dir / session["public_file"]
            if path.is_symlink() or not path.is_file() or _file_digest(path.read_bytes()) != session["public_digest"]:
                raise StudyError("public playtest page missing or digest mismatch")
    counts = {"AI_ONLY": 0, "HUMAN_AI": 0, "NO_CLEAR_DIFFERENCE": 0, "INCONCLUSIVE": 0}
    by_order = {"AI_FIRST": {k: 0 for k in counts}, "HUMAN_FIRST": {k: 0 for k in counts}}
    n = 0
    eligible_n = 0
    not_played_both_n = 0
    record_digests = []
    for file in sorted((private_dir / "responses").glob("*.json")):
        row = _read(file)
        keys(row, {"schema_version", "plan_digest", "public_digest", "response", "evidence_source"}, "record")
        sid, answer = validate_response(row["response"], state)
        if (file.name != sid + ".json" or row["plan_digest"] != state["plan_digest"]
                or row["public_digest"] != state["sessions"][sid]["public_digest"]
                or row["evidence_source"] != "PARTICIPANT_REPORTED_UNVERIFIED"):
            raise StudyError("response provenance/binding mismatch")
        n += 1
        record_digests.append(_file_digest(file.read_bytes()))
        if not answer["self_reported_played_both"]:
            not_played_both_n += 1
            continue  # A non-player report cannot contribute to preference or paired sample.
        eligible_n += 1
        first_origin = state["plan"]["variants"][state["sessions"][sid]["order"][0]]["origin"]
        bucket = "AI_FIRST" if first_origin == "AI_ONLY" else "HUMAN_FIRST"
        choice = answer["choice"]
        if choice.startswith("A_") or choice.startswith("B_"):
            index = 0 if choice.startswith("A_") else 1
            result = state["plan"]["variants"][state["sessions"][sid]["order"][index]]["origin"]
        else:
            result = choice
        counts[result] += 1
        by_order[bucket][result] += 1
    plan = state["plan"]
    observed = [v["usage"] for v in plan["variants"]]
    usage_equal = observed[0] == observed[1]
    if eligible_n == 0:
        status = "NO_OBSERVED_PLAYER_PREFERENCES"
    elif eligible_n < plan["playtest"]["planned_min_responses"]:
        status = "DESCRIPTIVE_BELOW_PREDECLARED_MINIMUM"
    else:
        status = "DESCRIPTIVE_ONLY_HUMAN_REVIEW_REQUIRED"
    return {"schema_version": 1, "study_id": plan["study_id"],
            "measurement_unit": "session_reports_not_verified_unique_players",
            "plan_digest": state["plan_digest"], "assignment_set_digest": state["assignment_set_digest"],
            "response_set_digest": digest_object(record_digests),
            "allocated_sessions": len(state["sessions"]), "recorded_responses": n,
            "paired_play_reports": eligible_n, "not_played_both_reports": not_played_both_n,
            "planned_min_responses": plan["playtest"]["planned_min_responses"],
            "status": status, "public_pages_verified": pages_verified,
            "counts_by_operator_declared_origin": counts,
            "order_breakdown": by_order,
            "production_resource_ceiling_shared": True,
            "actual_reported_resource_usage_equal": usage_equal,
            "playtest": plan["playtest"],
            "limitations": ["Source attribution and Candidate/Evaluation evidence were supplied by the operator, not independently verified by this script.",
                            "Neither unique-human identity nor independent participant recruitment is verified; paired play, sequence and duration are self-reported; no population inference.",
                            "Candidate links or gameplay may leak provenance; sequential page display guides but cannot prove actual exposure order.",
                            "No Review, lifecycle decision, causal effect or paid willingness-to-pay is inferred."],
            "authority": "LOCAL_NON_AUTHORITATIVE_NOT_LEDGER_EVIDENCE"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local, non-authoritative blind AI/human-AI playtest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--plan", type=pathlib.Path, required=True)
    p.add_argument("--private-dir", type=pathlib.Path, required=True)
    p.add_argument("--public-dir", type=pathlib.Path, required=True)
    p.add_argument("--sessions", type=int, default=4)
    p = sub.add_parser("record")
    p.add_argument("--private-dir", type=pathlib.Path, required=True)
    p.add_argument("--response", type=pathlib.Path, required=True)
    p = sub.add_parser("report")
    p.add_argument("--private-dir", type=pathlib.Path, required=True)
    p.add_argument("--public-dir", type=pathlib.Path, default=None,
                   help="optional: verify every generated A/B page against its SHA-256")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "prepare":
            result = prepare(args.plan, args.private_dir, args.public_dir, args.sessions)
        elif args.cmd == "record":
            result = record(args.private_dir, args.response)
        else:
            result = report(args.private_dir, args.public_dir)
    except (StudyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
