from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import tomllib
import uuid
from typing import Any

from bootstrap import _managed_paths
from companion_skills import (
    CompanionSkillSyncError,
    CompanionSkillSynchronizer,
    companion_target_paths,
    companion_targets,
)


class HarnessInstallError(RuntimeError):
    pass


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: pathlib.Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = pathlib.Path(raw)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _atomic_replace_dir(source: pathlib.Path, target: pathlib.Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(target.name + ".backup-" + uuid.uuid4().hex)
    had_target = target.exists()
    try:
        if had_target:
            target.rename(backup)
        source.rename(target)
    except Exception:
        if not target.exists() and backup.exists():
            backup.rename(target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def _write_live_locked_file(path: pathlib.Path, content: bytes) -> None:
    """Last-resort Windows fallback when delete-sharing blocks os.replace.

    The old bytes are copied to a sibling recovery file before the direct
    overwrite. If the overwrite raises, the old bytes are restored in-place.
    This path is used only after atomic replacement was denied.
    """
    if not path.exists():
        raise PermissionError(f"target disappeared before live overwrite: {path}")
    backup = path.with_name(path.name + ".live-backup-" + uuid.uuid4().hex)
    shutil.copy2(path, backup)
    try:
        with path.open("r+b") as fh:
            fh.seek(0)
            fh.write(content)
            fh.truncate()
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        old = backup.read_bytes()
        with path.open("r+b") as fh:
            fh.seek(0)
            fh.write(old)
            fh.truncate()
            fh.flush()
            os.fsync(fh.fileno())
        raise
    else:
        backup.unlink(missing_ok=True)


def _write_file_with_live_fallback(path: pathlib.Path, content: bytes) -> str:
    """Write one managed file, tolerating a Windows reader that denies rename.

    Prefer atomic replacement. When the existing file is live and Windows
    rejects rename/delete-sharing, use the same backed-up in-place overwrite
    already used for locked runtime files. Missing targets still fail closed:
    a denied atomic create is not equivalent to a safe live overwrite.
    """
    try:
        _atomic_write(path, content)
        return "atomic-replace"
    except PermissionError:
        if not path.is_file():
            raise
        _write_live_locked_file(path, content)
        return "live-overwrite"


def _sync_tree_filewise(source: pathlib.Path, target: pathlib.Path) -> bool:
    """Fallback for Windows when a live process keeps the target directory open.

    Prefer per-file atomic replacement. If a reader denies delete-sharing for a
    specific existing file, fall back to a backed-up in-place overwrite for
    that file only. Extra target files are left in place.
    """
    target.mkdir(parents=True, exist_ok=True)
    used_live_overwrite = False
    for src in sorted(p for p in source.rglob("*") if p.is_file()):
        rel = src.relative_to(source)
        dst = target / rel
        content = src.read_bytes()
        mode = _write_file_with_live_fallback(dst, content)
        if mode == "live-overwrite":
            used_live_overwrite = True
    return used_live_overwrite


def _copy_tree_atomic(source: pathlib.Path, target: pathlib.Path) -> str:
    stage = target.with_name(target.name + ".stage-" + uuid.uuid4().hex)
    try:
        shutil.copytree(source, stage)
        try:
            _atomic_replace_dir(stage, target)
            return "directory-swap"
        except PermissionError:
            used_live = _sync_tree_filewise(stage, target)
            return "filewise-live-fallback" if used_live else "filewise-fallback"
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _managed_digest(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for rel in sorted(_managed_paths()):
        path = root / rel
        if not path.is_file():
            raise HarnessInstallError(f"managed runtime file is missing: {rel}")
        rel_bytes = rel.encode("utf-8")
        content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest.update(len(rel_bytes).to_bytes(4, "big"))
        digest.update(rel_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


class _InstallSnapshot:
    def __init__(self, targets: list[pathlib.Path]):
        unique: list[pathlib.Path] = []
        seen: set[pathlib.Path] = set()
        for target in targets:
            resolved = target.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(resolved)
        self._temp = tempfile.TemporaryDirectory(prefix="game-exp-install-rollback-")
        self._root = pathlib.Path(self._temp.name)
        self._entries: list[tuple[pathlib.Path, str, pathlib.Path | None]] = []
        for index, target in enumerate(unique):
            backup = self._root / str(index)
            if target.is_dir():
                shutil.copytree(target, backup)
                kind = "dir"
            elif target.is_file():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                kind = "file"
            elif target.exists():
                raise HarnessInstallError(f"unsupported install target type: {target}")
            else:
                backup = None
                kind = "missing"
            self._entries.append((target, kind, backup))

    def restore(self) -> None:
        errors: list[str] = []
        for target, kind, backup in reversed(self._entries):
            try:
                if kind == "missing":
                    if target.is_dir():
                        shutil.rmtree(target)
                    elif target.exists():
                        target.unlink()
                    continue
                if backup is None:
                    raise HarnessInstallError(f"rollback backup missing for {target}")
                if kind == "file":
                    if target.is_dir():
                        shutil.rmtree(target)
                    _write_file_with_live_fallback(target, backup.read_bytes())
                    continue
                if target.is_file():
                    target.unlink()
                _copy_tree_atomic(backup, target)
            except Exception as exc:
                errors.append(f"{target}: {exc}")
        if errors:
            raise HarnessInstallError(
                "install rollback was incomplete: " + "; ".join(errors)
            )

    def close(self) -> None:
        self._temp.cleanup()


def _remove_toml_table(text: str, table_prefix: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            header = stripped.strip("[]").strip()
            skip = header == table_prefix or header.startswith(table_prefix + ".")
        if not skip:
            out.append(line)
    return "".join(out).rstrip() + ("\n" if out else "")


SUPPORTED_HARNESSES = ("codex", "qoder", "cursor")
CANONICAL_SOURCE = "https://github.com/siskosun/game-exp"


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    parts = value.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


class HarnessInstaller:
    def __init__(
        self,
        source_root: pathlib.Path,
        home: pathlib.Path,
        *,
        harness: str,
        runtime_dir: pathlib.Path | None = None,
        allow_downgrade: bool = False,
    ):
        if harness not in SUPPORTED_HARNESSES:
            raise HarnessInstallError(
                f"unsupported harness {harness!r}; choose one of "
                + ", ".join(SUPPORTED_HARNESSES)
            )
        self.source_root = source_root.resolve()
        self.home = home.resolve()
        self.harness = harness
        self.allow_downgrade = allow_downgrade
        self.runtime_dir = (
            runtime_dir.resolve()
            if runtime_dir is not None
            else self.home / ".game-exp" / "runtimes" / harness
        )
        self.plugin_path = self.source_root / "plugins" / "game-exp" / "plugin.json"
        self.skill_source = self.source_root / "plugins" / "game-exp" / "skills" / "game-exp"
        self.version = self._load_version()

    def _load_version(self) -> str:
        try:
            value = json.loads(self.plugin_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HarnessInstallError(f"invalid source plugin.json: {exc}") from exc
        version = value.get("version") if isinstance(value, dict) else None
        if not isinstance(version, str) or not version:
            raise HarnessInstallError("source plugin.json is missing version")
        return version

    def _validate_source(self) -> None:
        missing = [
            rel
            for rel in _managed_paths()
            if not (self.source_root / rel).is_file()
        ]
        if missing:
            raise HarnessInstallError(
                "source runtime is incomplete: " + ", ".join(sorted(missing))
            )
        skill = self.skill_source / "SKILL.md"
        icon = self.skill_source / "assets" / "icon.svg"
        if not skill.read_text(encoding="utf-8").startswith("---\n"):
            raise HarnessInstallError("source SKILL.md frontmatter is invalid")
        icon_bytes = icon.read_bytes()
        if len(icon_bytes) < 64 or b"<svg" not in icon_bytes[:512].lower():
            raise HarnessInstallError("source icon.svg is missing or corrupted")

    def _stage_runtime(self) -> pathlib.Path:
        stage = self.runtime_dir.with_name(
            self.runtime_dir.name + ".stage-" + uuid.uuid4().hex
        )
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.mkdir(parents=False, exist_ok=False)
        try:
            for rel in _managed_paths():
                src = self.source_root / rel
                dst = stage / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            source_digest = _managed_digest(self.source_root)
            (stage / "VERSION.txt").write_text(self.version + "\n", encoding="utf-8")
            (stage / "INSTALL_SOURCE.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "source": CANONICAL_SOURCE,
                        "version": self.version,
                        "harness": self.harness,
                        "source_digest": source_digest,
                        "digest_algorithm": "sha256-managed-runtime-v1",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            self._validate_runtime(stage)
            return stage
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def _validate_runtime(self, root: pathlib.Path) -> None:
        plugin = json.loads(
            (root / "plugins" / "game-exp" / "plugin.json").read_text(encoding="utf-8")
        )
        if plugin.get("version") != self.version:
            raise HarnessInstallError("staged plugin version mismatch")
        if (root / "VERSION.txt").read_text(encoding="utf-8").strip() != self.version:
            raise HarnessInstallError("staged VERSION.txt mismatch")
        if not (root / "tools" / "game-exp" / "mcp_server.py").is_file():
            raise HarnessInstallError("staged MCP server is missing")
        provenance = json.loads(
            (root / "INSTALL_SOURCE.json").read_text(encoding="utf-8")
        )
        expected_digest = _managed_digest(self.source_root)
        actual_digest = _managed_digest(root)
        if provenance != {
            "schema_version": 2,
            "source": CANONICAL_SOURCE,
            "version": self.version,
            "harness": self.harness,
            "source_digest": expected_digest,
            "digest_algorithm": "sha256-managed-runtime-v1",
        }:
            raise HarnessInstallError("staged install provenance mismatch")
        if actual_digest != expected_digest:
            raise HarnessInstallError("staged managed-runtime digest mismatch")
        icon = root / "plugins" / "game-exp" / "skills" / "game-exp" / "assets" / "icon.svg"
        raw = icon.read_bytes()
        if len(raw) < 64 or b"<svg" not in raw[:512].lower():
            raise HarnessInstallError("staged icon.svg is corrupted")

    @property
    def mcp_script(self) -> pathlib.Path:
        return self.runtime_dir / "tools" / "game-exp" / "mcp_server.py"

    @property
    def skill_target(self) -> pathlib.Path:
        roots = {
            "codex": self.home / ".codex" / "skills" / "game-exp",
            "qoder": self.home / ".qoder" / "skills" / "game-exp",
            "cursor": self.home / ".cursor" / "skills" / "game-exp",
        }
        return roots[self.harness]

    @property
    def config_path(self) -> pathlib.Path:
        paths = {
            "codex": self.home / ".codex" / "config.toml",
            "qoder": self.home / ".qoder" / "settings.json",
            "cursor": self.home / ".cursor" / "mcp.json",
        }
        return paths[self.harness]

    def _preflight_config(self) -> None:
        path = self.config_path
        if not path.exists():
            return
        if self.harness == "codex":
            try:
                tomllib.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise HarnessInstallError(f"invalid Codex TOML config {path}: {exc}") from exc
            return

        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HarnessInstallError(f"invalid JSON config {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise HarnessInstallError(f"JSON config must be an object: {path}")
        servers = value.get("mcpServers")
        if servers is not None and not isinstance(servers, dict):
            raise HarnessInstallError(f"mcpServers must be an object: {path}")

    def installed_version(self) -> str | None:
        marker = self.runtime_dir / "VERSION.txt"
        if not marker.is_file():
            return None
        value = marker.read_text(encoding="utf-8").strip()
        return value or None

    def _validate_installed_config(self) -> None:
        path = self.config_path
        if not path.is_file():
            raise HarnessInstallError("selected Harness MCP config is missing")
        if self.harness == "codex":
            value = tomllib.loads(path.read_text(encoding="utf-8"))
            servers = value.get("mcp_servers")
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            servers = value.get("mcpServers") if isinstance(value, dict) else None
        if not isinstance(servers, dict):
            raise HarnessInstallError("selected Harness MCP server table is missing")
        entry = servers.get("game-exp")
        if not isinstance(entry, dict):
            raise HarnessInstallError("selected Harness game-exp MCP entry is missing")
        if entry.get("command") != "uv":
            raise HarnessInstallError("selected Harness game-exp MCP command drifted")
        args = entry.get("args")
        if not isinstance(args, list) or not args:
            raise HarnessInstallError("selected Harness game-exp MCP args are missing")
        try:
            configured_script = pathlib.Path(str(args[-1])).resolve()
        except Exception as exc:
            raise HarnessInstallError("selected Harness game-exp MCP path is invalid") from exc
        if configured_script != self.mcp_script.resolve():
            raise HarnessInstallError("selected Harness game-exp MCP path drifted")

    def _same_version_install_detail(self) -> tuple[bool, str | None, str | None]:
        installed_digest = None
        try:
            provenance = json.loads(
                (self.runtime_dir / "INSTALL_SOURCE.json").read_text(encoding="utf-8")
            )
            if isinstance(provenance, dict):
                raw_digest = provenance.get("source_digest")
                if isinstance(raw_digest, str):
                    installed_digest = raw_digest
            self._validate_runtime(self.runtime_dir)
            if not (self.skill_target / "SKILL.md").is_file():
                raise HarnessInstallError("installed game-exp Skill entrypoint is missing")
            if not (self.skill_target / "agents" / "openai.yaml").is_file():
                raise HarnessInstallError("installed game-exp Skill metadata is missing")
            self._validate_installed_config()
        except Exception as exc:
            return False, str(exc), installed_digest
        return True, None, installed_digest

    def legacy_shared_state(self) -> dict[str, Any]:
        runtime = self.home / ".agents" / "tools" / "game-exp"
        skill = self.home / ".agents" / "skills" / "game-exp"
        marker = runtime / "VERSION.txt"
        version = (
            marker.read_text(encoding="utf-8").strip()
            if marker.is_file()
            else None
        )
        return {
            "detected": runtime.exists() or skill.exists(),
            "runtime_dir": str(runtime),
            "runtime_exists": runtime.exists(),
            "runtime_version": version or None,
            "skill_dir": str(skill),
            "skill_exists": skill.exists(),
            "cleanup_requires_explicit_all": True,
        }

    def plan(self) -> dict[str, Any]:
        self._validate_source()
        source_digest = _managed_digest(self.source_root)
        installed = self.installed_version()
        installed_digest = None
        reason = None
        footprint = self.runtime_dir.exists() or self.skill_target.exists()
        if installed is None:
            if footprint:
                state = "UPGRADE_AVAILABLE"
                reason = "INSTALLED_FOOTPRINT_INCOMPLETE"
            else:
                state = "NOT_INSTALLED"
        elif installed == self.version:
            valid, detail, installed_digest = self._same_version_install_detail()
            if valid:
                state = "CURRENT"
            else:
                state = "UPGRADE_AVAILABLE"
                reason = "SAME_VERSION_INSTALL_DRIFT"
                if detail:
                    reason += ": " + detail
        else:
            source_tuple = _version_tuple(self.version)
            installed_tuple = _version_tuple(installed)
            if source_tuple is None or installed_tuple is None:
                state = "VERSION_UNCOMPARABLE"
            elif installed_tuple < source_tuple:
                state = "UPGRADE_AVAILABLE"
                reason = "VERSION_UPGRADE"
            else:
                state = "SOURCE_OLDER_THAN_INSTALLED"
        return {
            "status": "PASS",
            "harness": self.harness,
            "source": CANONICAL_SOURCE,
            "source_version": self.version,
            "source_digest": source_digest,
            "installed_version": installed,
            "installed_digest": installed_digest,
            "install_state": state,
            "install_reason": reason,
            "runtime_dir": str(self.runtime_dir),
            "would_update_other_harnesses": False,
            "would_sync_companion_skills": True,
            "companion_skills": companion_targets(),
            "legacy_shared": self.legacy_shared_state(),
        }

    def _guard_downgrade(self) -> None:
        plan = self.plan()
        if (
            plan["install_state"] == "SOURCE_OLDER_THAN_INSTALLED"
            and not self.allow_downgrade
        ):
            raise HarnessInstallError(
                "source version is older than the installed Harness runtime; "
                "use --allow-downgrade only for an explicit rollback"
            )

    def preflight(self) -> None:
        if sys.version_info < (3, 11):
            raise HarnessInstallError(
                "game-exp requires Python 3.11 or newer"
            )
        self._validate_source()
        self._guard_downgrade()
        if shutil.which("uv") is None:
            raise HarnessInstallError(
                "uv is required for the game-exp MCP command but was not found in PATH"
            )
        self._preflight_config()

    def _install_runtime(self) -> str:
        stage = self._stage_runtime()
        old_cwd = pathlib.Path.cwd()
        mode = "directory-swap"
        try:
            os.chdir(self.home)
            try:
                _atomic_replace_dir(stage, self.runtime_dir)
            except PermissionError:
                used_live = _sync_tree_filewise(stage, self.runtime_dir)
                mode = "filewise-live-fallback" if used_live else "filewise-fallback"
        finally:
            try:
                os.chdir(old_cwd)
            except OSError:
                os.chdir(self.home)
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
        self._validate_runtime(self.runtime_dir)
        return mode

    def _install_skill(self) -> str:
        source = self.runtime_dir / "plugins" / "game-exp" / "skills" / "game-exp"
        return _copy_tree_atomic(source, self.skill_target)

    def _mcp_json_entry(self) -> dict[str, Any]:
        return {
            "type": "stdio",
            "command": "uv",
            "args": [
                "run",
                "--with",
                "mcp==2.2.0",
                "python",
                str(self.mcp_script),
            ],
        }

    def _install_codex(self) -> pathlib.Path:
        path = self.config_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        text = _remove_toml_table(text, "mcp_servers.game-exp")
        args = json.dumps(self._mcp_json_entry()["args"], ensure_ascii=False)
        command = json.dumps("uv")
        block = (
            "[mcp_servers.game-exp]\n"
            f"command = {command}\n"
            f"args = {args}\n"
            "enabled = true\n"
        )
        if text and not text.endswith("\n"):
            text += "\n"
        if text.strip():
            text += "\n"
        text += block
        tomllib.loads(text)
        _write_file_with_live_fallback(path, text.encode("utf-8"))
        return path

    def _install_json_mcp(self) -> pathlib.Path:
        path = self.config_path
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise HarnessInstallError(f"invalid JSON config {path}: {exc}") from exc
            if not isinstance(value, dict):
                raise HarnessInstallError(f"JSON config must be an object: {path}")
        else:
            value = {}
        servers = value.get("mcpServers")
        if servers is None:
            servers = {}
            value["mcpServers"] = servers
        if not isinstance(servers, dict):
            raise HarnessInstallError(f"mcpServers must be an object: {path}")
        servers["game-exp"] = self._mcp_json_entry()
        encoded = _json_bytes(value)
        json.loads(encoded.decode("utf-8"))
        _write_file_with_live_fallback(path, encoded)
        return path

    def _install_config(self) -> pathlib.Path:
        if self.harness == "codex":
            return self._install_codex()
        return self._install_json_mcp()

    def _install_after_preflight(
        self,
        companion_skills: list[dict[str, Any]],
    ) -> dict[str, Any]:
        runtime_update_mode = self._install_runtime()
        skill_update_mode = self._install_skill()
        config = self._install_config()
        return {
            "status": "PASS",
            "version": self.version,
            "harness": self.harness,
            "updated_harnesses": [self.harness],
            "runtime_dir": str(self.runtime_dir),
            "mcp_script": str(self.mcp_script),
            "runtime_update_mode": runtime_update_mode,
            "skill": str(self.skill_target),
            "skill_update_mode": skill_update_mode,
            "config": str(config),
            "companion_skills": companion_skills,
            "repo_binding": "dynamic",
            "shared_runtime": False,
            "next_zh": (
                f"仅已更新 {self.harness} 的 game-exp runtime、Skill 与 MCP 配置，"
                "并同步该 Harness 的 Godot Prototype Studio 与 H5 Game Prototype Agent 最新版本；"
                "其他 Harness 未被修改。新会话应显式把当前 owner/repo 传给 game_exp_* 工具。"
            ),
        }

    def _transaction_targets(self) -> list[pathlib.Path]:
        return [
            self.runtime_dir,
            self.skill_target,
            self.config_path,
            *companion_target_paths(self.home, self.harness),
        ]

    def install(self) -> dict[str, Any]:
        self.preflight()
        snapshot = _InstallSnapshot(self._transaction_targets())
        try:
            companions = CompanionSkillSynchronizer(
                self.home,
                harness=self.harness,
            ).sync()
            return self._install_after_preflight(companions)
        except Exception as exc:
            try:
                snapshot.restore()
            except Exception as rollback_exc:
                raise HarnessInstallError(
                    f"install failed ({exc}); rollback also failed ({rollback_exc})"
                ) from exc
            raise
        finally:
            snapshot.close()


def install_many(
    source_root: pathlib.Path,
    home: pathlib.Path,
    harnesses: tuple[str, ...],
    *,
    allow_downgrade: bool = False,
    cleanup_legacy_shared: bool = False,
) -> dict[str, Any]:
    installers = [
        HarnessInstaller(
            source_root,
            home,
            harness=harness,
            allow_downgrade=allow_downgrade,
        )
        for harness in harnesses
    ]
    for installer in installers:
        installer.preflight()
    transaction_targets = [
        target
        for installer in installers
        for target in installer._transaction_targets()
    ]
    snapshot = _InstallSnapshot(transaction_targets)
    try:
        companion_results = {
            installer.harness: CompanionSkillSynchronizer(
                home,
                harness=installer.harness,
            ).sync()
            for installer in installers
        }
        results = {
            installer.harness: installer._install_after_preflight(
                companion_results[installer.harness]
            )
            for installer in installers
        }
    except Exception as exc:
        try:
            snapshot.restore()
        except Exception as rollback_exc:
            raise HarnessInstallError(
                f"multi-Harness install failed ({exc}); rollback also failed ({rollback_exc})"
            ) from exc
        raise
    finally:
        snapshot.close()
    versions = {row["version"] for row in results.values()}
    if len(versions) != 1:
        raise HarnessInstallError("multi-Harness install produced inconsistent versions")

    legacy_cleanup = {
        "requested": cleanup_legacy_shared,
        "performed": False,
        "removed": [],
    }
    if cleanup_legacy_shared:
        legacy_paths = [
            home / ".agents" / "tools" / "game-exp",
            home / ".agents" / "skills" / "game-exp",
        ]
        for path in legacy_paths:
            if path.exists():
                shutil.rmtree(path)
                legacy_cleanup["removed"].append(str(path))
        legacy_cleanup["performed"] = True

    return {
        "status": "PASS",
        "version": next(iter(versions)),
        "harness": "all",
        "updated_harnesses": list(harnesses),
        "results": results,
        "repo_binding": "dynamic",
        "shared_runtime": False,
        "legacy_cleanup": legacy_cleanup,
        "next_zh": (
            "已按显式 all 请求分别更新 Codex/Qoder/Cursor，并为每个 Harness 同步 GPS/H5 最新技能；"
            "三个 Harness 使用彼此独立的 runtime，不再因单 Harness 升级而联动。"
        ),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or upgrade game-exp for one Harness without touching the others"
    )
    parser.add_argument(
        "--source-root",
        default=str(pathlib.Path(__file__).resolve().parents[2]),
    )
    parser.add_argument("--home", default=str(pathlib.Path.home()))
    parser.add_argument(
        "--harness",
        required=True,
        choices=(*SUPPORTED_HARNESSES, "all"),
        help="Harness to install/upgrade; use all only when explicitly requested",
    )
    parser.add_argument(
        "--runtime-dir",
        help="custom runtime path; valid only when installing one Harness",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report install/upgrade status without writing files",
    )
    parser.add_argument(
        "--allow-downgrade",
        action="store_true",
        help="allow an explicit rollback to an older source version",
    )
    parser.add_argument(
        "--cleanup-legacy-shared",
        action="store_true",
        help=(
            "after an explicit --harness all migration, remove the old shared "
            "~/.agents runtime and Skill"
        ),
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        source_root = pathlib.Path(args.source_root)
        home = pathlib.Path(args.home)
        if args.harness == "all":
            if args.runtime_dir:
                raise HarnessInstallError("--runtime-dir cannot be combined with --harness all")
            if args.check and args.cleanup_legacy_shared:
                raise HarnessInstallError(
                    "--cleanup-legacy-shared cannot be combined with --check"
                )
            installers = [
                HarnessInstaller(
                    source_root,
                    home,
                    harness=harness,
                    allow_downgrade=args.allow_downgrade,
                )
                for harness in SUPPORTED_HARNESSES
            ]
            if args.check:
                result = {
                    "status": "PASS",
                    "version": installers[0].version,
                    "harness": "all",
                    "updated_harnesses": [],
                    "plans": {
                        installer.harness: installer.plan()
                        for installer in installers
                    },
                    "would_update_other_harnesses": False,
                    "would_sync_companion_skills": True,
                    "companion_skills": companion_targets(),
                }
            else:
                result = install_many(
                    source_root,
                    home,
                    SUPPORTED_HARNESSES,
                    allow_downgrade=args.allow_downgrade,
                    cleanup_legacy_shared=args.cleanup_legacy_shared,
                )
        else:
            if args.cleanup_legacy_shared:
                raise HarnessInstallError(
                    "--cleanup-legacy-shared requires --harness all"
                )
            installer = HarnessInstaller(
                source_root,
                home,
                harness=args.harness,
                runtime_dir=pathlib.Path(args.runtime_dir) if args.runtime_dir else None,
                allow_downgrade=args.allow_downgrade,
            )
            result = installer.plan() if args.check else installer.install()
    except (
        HarnessInstallError,
        CompanionSkillSyncError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        result = {"status": "FAIL", "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL\t{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"PASS\tgame-exp {result['version']}")
        print("updated\t" + ",".join(result["updated_harnesses"]))
        if result.get("runtime_dir"):
            print(f"runtime\t{result['runtime_dir']}")
        else:
            for harness, row in result["results"].items():
                print(f"{harness}\t{row['runtime_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
