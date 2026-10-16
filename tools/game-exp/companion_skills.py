from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any

GITHUB_API = "https://api.github.com"
GITHUB_CODELOAD = "https://codeload.github.com"
_RUNTIME_FILES = {"SKILL.md", "VERSION"}
_RUNTIME_TOP = {"agents", "assets", "references", "scripts", "templates"}
_EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".probe",
    ".prototype",
    "__pycache__",
    "audit",
    "dev",
    "dist",
    "node_modules",
    "tests",
}
_EXCLUDED_FILES = {"CHANGELOG.md", "README.md", "README.zh-CN.md", "probes.jsonl"}
_SEMVER_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_MAX_ARCHIVE_MEMBERS = 4096
_MAX_ARCHIVE_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024
_MAX_ARCHIVE_COMPRESSION_RATIO = 500.0


class CompanionSkillSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompanionSkillSpec:
    name: str
    repository: str


COMPANION_SKILLS = (
    CompanionSkillSpec(
        name="godot-prototype-studio",
        repository="siskosun/godot-prototype-studio",
    ),
    CompanionSkillSpec(
        name="h5-game-prototype-agent",
        repository="siskosun/h5-game-prototype-agent",
    ),
)


def _request_bytes(url: str, *, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "game-exp-companion-sync/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CompanionSkillSyncError(f"GitHub request failed for {url}: {exc}") from exc


def _latest_semver_tag(repository: str) -> str:
    raw = _request_bytes(f"{GITHUB_API}/repos/{repository}/tags?per_page=100")
    try:
        rows = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionSkillSyncError(
            f"invalid GitHub tags response for {repository}: {exc}"
        ) from exc
    if not isinstance(rows, list):
        raise CompanionSkillSyncError(f"unexpected GitHub tags response for {repository}")
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str):
            continue
        match = _SEMVER_TAG.fullmatch(name.strip())
        if match:
            candidates.append((tuple(int(part) for part in match.groups()), name))
    if not candidates:
        raise CompanionSkillSyncError(
            f"{repository} has no semantic version tag; refusing to sync an unversioned branch"
        )
    candidates.sort()
    return candidates[-1][1]



_SNAPSHOT_FILE = pathlib.Path(__file__).with_name("companion-compatibility.lock.json")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _load_vetted_snapshot() -> dict[str, Any]:
    """Ship-time pinned companion baseline, not a mutable live GO-main dependency."""
    if _SNAPSHOT_FILE.is_symlink() or not _SNAPSHOT_FILE.is_file():
        raise CompanionSkillSyncError("companion compatibility snapshot is missing")
    try:
        raw = _SNAPSHOT_FILE.read_bytes()
    except OSError as exc:
        raise CompanionSkillSyncError("cannot read companion compatibility snapshot") from exc
    if len(raw) > 128 * 1024:
        raise CompanionSkillSyncError("companion snapshot exceeds size limit")
    try:
        lock = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise CompanionSkillSyncError("invalid companion snapshot") from exc
    if not isinstance(lock, dict):
        raise CompanionSkillSyncError("invalid companion snapshot object")
    return lock


def _vetted_companion_pins(specs: tuple[CompanionSkillSpec, ...]) -> dict[str, dict[str, str]]:
    """Use only reviewed, immutable released pins for the actual shipped companions.

    Custom test/dev specs retain the existing latest-tag route. Invalid lock,
    moved tag, or missing published Release fails before any local Skill writes.
    """
    if tuple(specs) != COMPANION_SKILLS:
        return {}
    lock = _load_vetted_snapshot()
    if lock.get("schema_version") != 1 or lock.get("policy") != "released-pins-only":
        raise CompanionSkillSyncError("unapproved companion compatibility policy")
    components = lock.get("components")
    if not isinstance(components, dict):
        raise CompanionSkillSyncError("vetted compatibility components unavailable")
    self_version_file = pathlib.Path(__file__).resolve().parents[2] / "VERSION.txt"
    try:
        current_version = self_version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CompanionSkillSyncError("game-exp source version is unavailable") from exc
    if lock.get("game_exp_version") != current_version:
        raise CompanionSkillSyncError("game-exp version does not match shipped companion snapshot")
    result: dict[str, dict[str, str]] = {}
    for spec in specs:
        entry = components.get(spec.name)
        if not isinstance(entry, dict) or entry.get("repository") != spec.repository:
            raise CompanionSkillSyncError("vetted companion repository does not match")
        tag, v = entry.get("tag"), entry.get("version")
        sha, skill_hash = entry.get("commit_sha"), entry.get("skill_git_blob_sha1")
        if (not isinstance(tag, str) or not _SEMVER_TAG.fullmatch(tag) or
            not isinstance(v, str) or tag.lstrip("v") != v or
            not isinstance(sha, str) or not _SHA40.fullmatch(sha) or
            not isinstance(skill_hash, str) or not _SHA40.fullmatch(skill_hash)):
            raise CompanionSkillSyncError("invalid pinned companion tag, version, or digest")
        release_raw = _request_bytes(f"{GITHUB_API}/repos/{spec.repository}/releases/tags/{tag}")
        try:
            release = json.loads(release_raw.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise CompanionSkillSyncError("companion Release metadata invalid") from exc
        if (not isinstance(release, dict) or release.get("tag_name") != tag or
            release.get("draft") or release.get("prerelease")):
            raise CompanionSkillSyncError("pinned companion must be a stable published Release")
        ref_raw = _request_bytes(f"{GITHUB_API}/repos/{spec.repository}/git/ref/tags/{tag}")
        try:
            ref = json.loads(ref_raw.decode("utf-8"))
            obj = ref["object"]
            if obj.get("type") == "tag":
                tag_raw = _request_bytes(f"{GITHUB_API}/repos/{spec.repository}/git/tags/{obj['sha']}")
                obj = json.loads(tag_raw.decode("utf-8"))["object"]
            actual = obj["sha"] if obj["type"] == "commit" else None
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise CompanionSkillSyncError("pinned companion tag cannot be resolved") from exc
        if actual != sha:
            raise CompanionSkillSyncError("pinned companion tag moved; refusing install")
        result[spec.name] = {"tag": tag, "version": v, "sha": sha, "skill_blob": skill_hash}
    return result


def _git_blob_sha(path: pathlib.Path) -> str:
    import hashlib
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _safe_extract(archive_path: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
    target_root = target.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if not members:
            raise CompanionSkillSyncError("downloaded archive is empty")
        if len(members) > _MAX_ARCHIVE_MEMBERS:
            raise CompanionSkillSyncError(
                f"downloaded archive has too many members: {len(members)}"
            )

        root_names: set[str] = set()
        total_bytes = 0
        validated: list[tuple[zipfile.ZipInfo, pathlib.Path]] = []
        for member in members:
            parts = pathlib.PurePosixPath(member.filename).parts
            if not parts:
                continue
            if member.flag_bits & 0x1:
                raise CompanionSkillSyncError(
                    f"encrypted archive member is not supported: {member.filename}"
                )

            mode = (member.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise CompanionSkillSyncError(
                    f"symbolic-link archive member is not allowed: {member.filename}"
                )

            if member.file_size > _MAX_ARCHIVE_MEMBER_BYTES:
                raise CompanionSkillSyncError(
                    f"archive member is too large: {member.filename}"
                )
            total_bytes += member.file_size
            if total_bytes > _MAX_ARCHIVE_TOTAL_BYTES:
                raise CompanionSkillSyncError(
                    "downloaded archive expands beyond the allowed size"
                )
            if member.file_size > 1024 * 1024:
                compressed = max(member.compress_size, 1)
                ratio = member.file_size / compressed
                if ratio > _MAX_ARCHIVE_COMPRESSION_RATIO:
                    raise CompanionSkillSyncError(
                        f"archive member compression ratio is too high: {member.filename}"
                    )

            root_names.add(parts[0])
            resolved = (target / pathlib.Path(*parts)).resolve()
            try:
                resolved.relative_to(target_root)
            except ValueError as exc:
                raise CompanionSkillSyncError(
                    f"unsafe archive path: {member.filename}"
                ) from exc
            validated.append((member, resolved))

        if len(root_names) != 1:
            raise CompanionSkillSyncError("downloaded archive has multiple roots")

        for member, destination in validated:
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, destination.open("wb") as sink:
                shutil.copyfileobj(source, sink)

    root = target / next(iter(root_names))
    if not root.is_dir():
        raise CompanionSkillSyncError("downloaded archive root is missing")
    return root


def _runtime_include(root: pathlib.Path, path: pathlib.Path) -> bool:
    if not path.is_file():
        return False
    rel = path.relative_to(root)
    parts = rel.parts
    if not parts:
        return False
    if rel.as_posix() in _RUNTIME_FILES:
        return True
    if parts[0] not in _RUNTIME_TOP:
        return False
    if any(part in _EXCLUDED_DIRS for part in parts):
        return False
    if path.name in _EXCLUDED_FILES:
        return False
    if path.name.startswith("ut-"):
        return False
    if path.suffix in {".pyc", ".log"}:
        return False
    return True


def _validate_skill(root: pathlib.Path, spec: CompanionSkillSpec, tag: str) -> str:
    skill = root / "SKILL.md"
    metadata = root / "agents" / "openai.yaml"
    version_file = root / "VERSION"
    if not skill.is_file() or not metadata.is_file() or not version_file.is_file():
        raise CompanionSkillSyncError(
            f"{spec.repository}@{tag} is missing SKILL.md, VERSION, or agents/openai.yaml"
        )
    text = skill.read_text(encoding="utf-8")
    if not text.startswith("---\n") or f"name: {spec.name}" not in text[:800]:
        raise CompanionSkillSyncError(
            f"{spec.repository}@{tag} has unexpected SKILL.md metadata"
        )
    version = version_file.read_text(encoding="utf-8").strip()
    normalized_tag = tag[1:] if tag.startswith("v") else tag
    if version != normalized_tag:
        raise CompanionSkillSyncError(
            f"{spec.repository}@{tag} VERSION={version!r} does not match tag"
        )
    return version


def _copy_runtime_tree(source: pathlib.Path, target: pathlib.Path) -> str:
    stage = target.with_name(target.name + ".stage-" + uuid.uuid4().hex)
    backup = target.with_name(target.name + ".backup-" + uuid.uuid4().hex)
    stage.mkdir(parents=True, exist_ok=False)
    try:
        for path in sorted(source.rglob("*")):
            if not _runtime_include(source, path):
                continue
            rel = path.relative_to(source)
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
        required = [
            stage / "SKILL.md",
            stage / "VERSION",
            stage / "agents" / "openai.yaml",
        ]
        if not all(path.is_file() for path in required):
            raise CompanionSkillSyncError("staged companion skill is incomplete")
        had_target = target.exists()
        if had_target:
            target.rename(backup)
        try:
            stage.rename(target)
        except Exception:
            if had_target and backup.exists() and not target.exists():
                backup.rename(target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return "directory-swap"
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if backup.exists() and target.exists():
            shutil.rmtree(backup, ignore_errors=True)


def _skill_root(home: pathlib.Path, harness: str) -> pathlib.Path:
    roots = {
        "codex": home / ".codex" / "skills",
        "qoder": home / ".qoder" / "skills",
        "cursor": home / ".cursor" / "skills",
    }
    try:
        return roots[harness]
    except KeyError as exc:
        raise CompanionSkillSyncError(f"unsupported harness for companion sync: {harness}") from exc


class CompanionSkillSynchronizer:
    def __init__(
        self,
        home: pathlib.Path,
        *,
        harness: str,
        specs: tuple[CompanionSkillSpec, ...] = COMPANION_SKILLS,
    ):
        self.home = home.resolve()
        self.harness = harness
        self.specs = specs

    def sync(self) -> list[dict[str, Any]]:
        pins = _vetted_companion_pins(self.specs)
        results: list[dict[str, Any]] = []
        skill_root = _skill_root(self.home, self.harness)
        skill_root.mkdir(parents=True, exist_ok=True)
        for spec in self.specs:
            approved = pins.get(spec.name)
            tag = approved["tag"] if approved else _latest_semver_tag(spec.repository)
            archive_url = (
                f"{GITHUB_CODELOAD}/{spec.repository}/zip/{approved['sha']}"
                if approved else f"{GITHUB_CODELOAD}/{spec.repository}/zip/refs/tags/{tag}"
            )
            with tempfile.TemporaryDirectory(prefix="game-exp-companion-") as td:
                temp = pathlib.Path(td)
                archive_path = temp / "source.zip"
                archive_path.write_bytes(_request_bytes(archive_url, timeout=60))
                extract_root = temp / "extract"
                extract_root.mkdir()
                source = _safe_extract(archive_path, extract_root)
                version = _validate_skill(source, spec, tag)
                if approved and _git_blob_sha(source / "SKILL.md") != approved["skill_blob"]:
                    raise CompanionSkillSyncError("pinned companion entrypoint digest mismatch")
                target = skill_root / spec.name
                mode = _copy_runtime_tree(source, target)
            results.append(
                {
                    "name": spec.name,
                    "repository": f"https://github.com/{spec.repository}",
                    "tag": tag,
                    "version": version,
                    "target": str(target),
                    "update_mode": mode,
                    "compatibility_basis": "shipped_release_snapshot" if approved else "custom_latest_semver_tag",
                }
            )
        return results


def companion_targets() -> list[dict[str, str]]:
    return [
        {
            "name": spec.name,
            "repository": f"https://github.com/{spec.repository}",
        }
        for spec in COMPANION_SKILLS
    ]


def companion_target_paths(home: pathlib.Path, harness: str) -> list[pathlib.Path]:
    skill_root = _skill_root(home.resolve(), harness)
    return [skill_root / spec.name for spec in COMPANION_SKILLS]
