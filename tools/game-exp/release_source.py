from __future__ import annotations

import json
import pathlib
import re
import tempfile
import urllib.parse
from dataclasses import dataclass
from typing import Any

from companion_skills import (
    CompanionSkillSyncError,
    _request_bytes,
    _safe_extract,
)

GITHUB_API = "https://api.github.com"
GITHUB_CODELOAD = "https://codeload.github.com"
GAME_EXP_REPOSITORY = "siskosun/game-exp"
CANONICAL_SOURCE = f"https://github.com/{GAME_EXP_REPOSITORY}"
_SEMVER_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class ReleaseSourceError(RuntimeError):
    pass


@dataclass
class ResolvedInstallSource:
    root: pathlib.Path
    channel: str
    ref: str
    version: str
    release_url: str | None = None
    _temp: tempfile.TemporaryDirectory[str] | None = None

    def close(self) -> None:
        if self._temp is not None:
            self._temp.cleanup()
            self._temp = None


def _json_request(url: str) -> Any:
    try:
        raw = _request_bytes(url)
    except CompanionSkillSyncError as exc:
        raise ReleaseSourceError(str(exc)) from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseSourceError(f"invalid GitHub response for {url}: {exc}") from exc


def _semver(tag: str) -> tuple[int, int, int] | None:
    match = _SEMVER_TAG.fullmatch(tag.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def _normalized_version(tag: str) -> str:
    value = _semver(tag)
    if value is None:
        raise ReleaseSourceError(f"release tag is not semantic version: {tag}")
    return ".".join(str(part) for part in value)


def _published_semver_releases() -> list[dict[str, Any]]:
    rows = _json_request(
        f"{GITHUB_API}/repos/{GAME_EXP_REPOSITORY}/releases?per_page=100"
    )
    if not isinstance(rows, list):
        raise ReleaseSourceError("unexpected GitHub releases response")
    releases: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("draft") is True or row.get("prerelease") is True:
            continue
        tag = row.get("tag_name")
        if not isinstance(tag, str):
            continue
        version = _semver(tag)
        if version is None:
            continue
        releases.append((version, row))
    if not releases:
        raise ReleaseSourceError(
            "game-exp has no published non-prerelease semantic-version Release"
        )
    releases.sort(key=lambda item: item[0])
    return [row for _version, row in releases]


def _select_release(requested: str | None) -> dict[str, Any]:
    releases = _published_semver_releases()
    if requested is None:
        return releases[-1]
    wanted = _semver(requested)
    if wanted is None:
        raise ReleaseSourceError(
            "--release must be a semantic version such as v1.3.0 or 1.3.0"
        )
    for row in releases:
        tag = row.get("tag_name")
        if isinstance(tag, str) and _semver(tag) == wanted:
            return row
    raise ReleaseSourceError(
        f"published stable Release not found for {requested}"
    )


def _validate_release_tree(root: pathlib.Path, tag: str) -> str:
    expected = _normalized_version(tag)
    try:
        marker = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
        plugin = json.loads(
            (root / "plugins/game-exp/plugin.json").read_text(encoding="utf-8")
        )
        install = json.loads((root / "INSTALL.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseSourceError(
            f"{tag} source archive is missing or invalid release metadata: {exc}"
        ) from exc
    values = {
        "tag": expected,
        "VERSION.txt": marker,
        "plugin.json": plugin.get("version") if isinstance(plugin, dict) else None,
        "INSTALL.json": install.get("version") if isinstance(install, dict) else None,
    }
    if len(set(values.values())) != 1:
        raise ReleaseSourceError(
            f"{tag} release metadata does not match its tag: {values}"
        )
    source = install.get("source_of_truth") if isinstance(install, dict) else None
    if source != CANONICAL_SOURCE:
        raise ReleaseSourceError(
            f"{tag} release source_of_truth is unexpected: {source!r}"
        )
    return expected


def resolve_install_source(
    source_root: pathlib.Path,
    *,
    channel: str = "stable",
    release: str | None = None,
) -> ResolvedInstallSource:
    source_root = source_root.resolve()
    if channel == "development":
        if release is not None:
            raise ReleaseSourceError(
                "--release cannot be combined with --channel development"
            )
        try:
            version = (
                source_root / "plugins/game-exp/plugin.json"
            ).read_text(encoding="utf-8")
            plugin = json.loads(version)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReleaseSourceError(
                f"development source is invalid: {exc}"
            ) from exc
        plugin_version = plugin.get("version") if isinstance(plugin, dict) else None
        if not isinstance(plugin_version, str) or _semver(plugin_version) is None:
            raise ReleaseSourceError(
                "development source plugin version is not semantic"
            )
        return ResolvedInstallSource(
            root=source_root,
            channel="development",
            ref="working-tree",
            version=plugin_version,
        )

    if channel != "stable":
        raise ReleaseSourceError(
            f"unsupported install channel {channel!r}; choose stable or development"
        )

    row = _select_release(release)
    tag = row.get("tag_name")
    if not isinstance(tag, str):
        raise ReleaseSourceError("selected Release is missing tag_name")
    release_url = row.get("html_url")
    if release_url is not None and not isinstance(release_url, str):
        release_url = None

    temp = tempfile.TemporaryDirectory(prefix="game-exp-release-source-")
    temp_root = pathlib.Path(temp.name)
    archive_path = temp_root / "source.zip"
    extract_root = temp_root / "extract"
    extract_root.mkdir()
    archive_url = (
        f"{GITHUB_CODELOAD}/{GAME_EXP_REPOSITORY}/zip/refs/tags/"
        f"{urllib.parse.quote(tag, safe='')}"
    )
    try:
        try:
            archive_path.write_bytes(_request_bytes(archive_url))
            root = _safe_extract(archive_path, extract_root)
        except CompanionSkillSyncError as exc:
            raise ReleaseSourceError(
                f"failed to fetch stable game-exp Release {tag}: {exc}"
            ) from exc
        version = _validate_release_tree(root, tag)
        return ResolvedInstallSource(
            root=root,
            channel="stable",
            ref=tag,
            version=version,
            release_url=release_url,
            _temp=temp,
        )
    except Exception:
        temp.cleanup()
        raise
