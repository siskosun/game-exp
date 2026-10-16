#!/usr/bin/env python3
"""Read-only vetted four-Skill version preflight. No automatic installation."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import urllib.error
import urllib.request

LOCK_URL = "https://raw.githubusercontent.com/siskosun/game-opportunity/main/skills/game-opportunity/compatibility.lock.json"
API = "https://api.github.com/repos/siskosun/"
NAMES = ("game-opportunity", "game-exp", "h5-game-prototype-agent", "godot-prototype-studio")
VERSION_RE = re.compile(r"^v?([0-9]+)[.]([0-9]+)[.]([0-9]+)$")
NAME_RE = re.compile(r"(?m)^name:[ \t]*(game-opportunity|game-exp|h5-game-prototype-agent|godot-prototype-studio)[ \t]*$")
HASH_RE = re.compile(r"^[0-9a-f]{40}$")


def semver(value):
    match = VERSION_RE.fullmatch(value) if isinstance(value, str) else None
    return tuple(int(n) for n in match.groups()) if match else None


def fetch_json(url):
    if url != LOCK_URL and not (url.startswith(API)
                                and url.endswith("/releases/latest")
                                and url[len(API):-len("/releases/latest")] in NAMES):
        raise ValueError("unapproved version metadata URL")
    req = urllib.request.Request(url, headers={"User-Agent": "four-game-skills-version-check/1.0",
                                              "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read(131073)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("version metadata inaccessible") from exc
    if len(raw) > 131072:
        raise ValueError("version metadata too large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid version metadata JSON") from exc


def blob_sha1(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Skill entrypoint absent or symlinked")
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def installed(root):
    version_path = root / "VERSION"
    if version_path.is_symlink() or not version_path.is_file():
        return {"status": "UNVERIFIED", "reason": "VERSION absent"}
    v = version_path.read_text(encoding="utf-8").strip()
    if semver(v) is None:
        return {"status": "UNVERIFIED", "reason": "VERSION invalid"}
    return {"status": "DETECTED", "version": v, "entrypoint": blob_sha1(root / "SKILL.md")}


def pin(lock, name):
    if not isinstance(lock, dict) or lock.get("schema_version") != 1 or lock.get("policy") != "released-pins-only":
        raise ValueError("registry policy invalid")
    if name == "game-opportunity":
        v = lock.get("bundle_version")
        if semver(v) is None:
            raise ValueError("registry main version invalid")
        return {"version": v, "min_version": v}
    row = lock.get("components", {}).get(name)
    if not isinstance(row, dict) or row.get("repository") != "siskosun/" + name:
        raise ValueError("registry component invalid")
    if not semver(row.get("version")) or not semver(row.get("min_version")) or not HASH_RE.fullmatch(str(row.get("skill_git_blob_sha1"))):
        raise ValueError("registry component version or entrypoint hash invalid")
    if semver(row["min_version"]) > semver(row["version"]):
        raise ValueError("registry minimum exceeds pin")
    return row


def compare(actual, expected):
    if actual.get("status") != "DETECTED":
        return "UNVERIFIED", actual.get("reason", "installed version unavailable")
    v = semver(actual["version"])
    if v < semver(expected["min_version"]):
        return "INCOMPATIBLE", "below vetted minimum"
    if v != semver(expected["version"]):
        return "UNVERIFIED", "installed version differs from exact vetted pin"
    if expected.get("skill_git_blob_sha1") and expected["skill_git_blob_sha1"] != actual["entrypoint"]:
        return "INCOMPATIBLE", "installed Skill entrypoint differs from vetted pin"
    return "CURRENT", "exact vetted version"


def evaluate(skill_root, *, harness=None, home=None, peers=(), fetch=fetch_json):
    report = {"status": "UNVERIFIED", "writes": False, "self": None, "peers": {},
              "latest_published": None, "assurance": "STATIC_VERSION_AND_ENTRYPOINT_ONLY",
              "trusted_game_exp_doctor": "NOT_RUN"}
    try:
        root = pathlib.Path(skill_root)
        text = (root / "SKILL.md").read_text(encoding="utf-8")[:1600]
        match = NAME_RE.search(text)
        if match is None:
            raise ValueError("Skill identity unavailable")
        name = match.group(1)
        report["self"] = name
        lock = fetch(LOCK_URL)
        self_pin = pin(lock, name)
        own = installed(root)
        status, reason = compare(own, self_pin)
        report.update({"status": status, "reason": reason, "installed_version": own.get("version"),
                       "vetted_version": self_pin["version"]})
        if status == "CURRENT":
            info = fetch(API + name + "/releases/latest")
            tag = info.get("tag_name") if isinstance(info, dict) and not info.get("draft") and not info.get("prerelease") else None
            if semver(tag) is None or semver(tag) < semver(own["version"]):
                raise ValueError("latest published stable Release unverifiable")
            report["latest_published"] = tag
            if semver(tag) > semver(own["version"]):
                report["status"] = "UPDATE_AVAILABLE"
        if peers:
            if harness not in ("codex", "cursor", "qoder"):
                raise ValueError("--harness is required to check installed peer Skills")
            base = pathlib.Path(home).expanduser() if home else pathlib.Path.home()
            for peer in peers:
                if peer not in NAMES or peer == name:
                    raise ValueError("unrecognized peer")
                location = base / ("." + harness) / "skills" / peer
                if location.is_symlink() or not location.is_dir():
                    result = ("UNVERIFIED", "required peer not installed")
                    value = None
                else:
                    p = installed(location)
                    result = compare(p, pin(lock, peer))
                    value = p.get("version")
                report["peers"][peer] = {"status": result[0], "reason": result[1], "version": value}
            states = {row["status"] for row in report["peers"].values()}
            if "INCOMPATIBLE" in states:
                report["status"] = "INCOMPATIBLE"
            elif "UNVERIFIED" in states and report["status"] != "INCOMPATIBLE":
                report["status"] = "UNVERIFIED"
    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as exc:
        report["status"] = "UNVERIFIED"
        report["reason"] = str(exc)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    parser.add_argument("--harness", choices=("codex", "cursor", "qoder"))
    parser.add_argument("--home", type=pathlib.Path)
    parser.add_argument("--peer", choices=NAMES, action="append", default=[])
    parser.add_argument("--gate", action="store_true", help="reject unverified cross-Skill handoff")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = evaluate(args.skill_root, harness=args.harness, home=args.home, peers=args.peer)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["status"] + " " + report.get("reason", ""))
    return 2 if args.gate and report["status"] not in ("CURRENT", "UPDATE_AVAILABLE") else 0


if __name__ == "__main__":
    raise SystemExit(main())
