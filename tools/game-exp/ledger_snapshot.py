from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class LedgerSnapshot:
    ref: str
    blob_shas: dict[str, str]
    objects: dict[str, Any]

    @property
    def paths(self) -> list[str]:
        return sorted(self.blob_shas)


def _default_cache_root() -> Path:
    configured = os.environ.get("GAME_EXP_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve() / "ledger"
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "game-exp" / "ledger"
    return Path.home() / ".cache" / "game-exp" / "ledger"


def _run_read(command: list[str], *, attempts: int = 3) -> subprocess.CompletedProcess[str]:
    last: subprocess.CompletedProcess[str] | None = None
    delays = (0.35, 0.9)
    for attempt in range(attempts):
        try:
            proc = subprocess.run(
                command,
                text=True,
                encoding="utf-8",
                errors="strict",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
            )
        except subprocess.TimeoutExpired as exc:
            if attempt + 1 >= attempts:
                raise SnapshotError(
                    f"idempotent GitHub read timed out: {' '.join(command[:3])}"
                ) from exc
            time.sleep(delays[min(attempt, len(delays) - 1)])
            continue
        except FileNotFoundError as exc:
            raise SnapshotError(f"required command not found: {command[0]}") from exc
        last = proc
        if proc.returncode == 0:
            return proc
        if attempt + 1 < attempts:
            time.sleep(delays[min(attempt, len(delays) - 1)])
    assert last is not None
    raise SnapshotError(
        f"idempotent GitHub read failed after {attempts} attempts "
        f"({last.returncode}): {last.stderr[-1200:]}"
    )


class LedgerSnapshotLoader:
    def __init__(
        self,
        repo: str,
        *,
        cache_root: Path | None = None,
        runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        chunk_size: int = 40,
    ):
        if "/" not in repo:
            raise SnapshotError("repo must be owner/name")
        self.repo = repo
        self.owner, self.name = repo.split("/", 1)
        self.cache_root = cache_root or _default_cache_root()
        self.runner = runner or _run_read
        self.chunk_size = max(1, min(int(chunk_size), 60))
        self._memory: dict[str, LedgerSnapshot] = {}

    def _repo_cache(self) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.repo)
        path = self.cache_root / safe
        path.mkdir(parents=True, exist_ok=True)
        (path / "blobs").mkdir(parents=True, exist_ok=True)
        return path

    def _json(self, command: list[str]) -> Any:
        proc = self.runner(command)
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SnapshotError("GitHub read returned invalid JSON") from exc

    def _index_path(self, ref: str) -> Path:
        return self._repo_cache() / f"{ref}.index.json"

    def _blob_path(self, sha: str) -> Path:
        return self._repo_cache() / "blobs" / f"{sha}.txt"

    def _tree_index(self, ref: str) -> dict[str, str]:
        index_path = self._index_path(ref)
        if index_path.is_file():
            try:
                value = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                value = None
            if isinstance(value, dict) and all(
                isinstance(path, str)
                and isinstance(sha, str)
                and SHA_RE.fullmatch(sha)
                for path, sha in value.items()
            ):
                return dict(value)

        data = self._json(
            ["gh", "api", f"repos/{self.repo}/git/trees/{ref}?recursive=1"]
        )
        if not isinstance(data, dict) or data.get("truncated") is True:
            raise SnapshotError("Ledger recursive tree response is invalid or truncated")
        rows = data.get("tree")
        if not isinstance(rows, list):
            raise SnapshotError("Ledger tree response is missing entries")
        result: dict[str, str] = {}
        for row in rows:
            if (
                isinstance(row, dict)
                and row.get("type") == "blob"
                and isinstance(row.get("path"), str)
                and isinstance(row.get("sha"), str)
                and SHA_RE.fullmatch(row["sha"])
            ):
                result[row["path"]] = row["sha"]
        temp = index_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temp.replace(index_path)
        return result

    def _fetch_blobs(
        self,
        ref: str,
        path_to_sha: dict[str, str],
        missing_paths: list[str],
    ) -> None:
        for offset in range(0, len(missing_paths), self.chunk_size):
            chunk = missing_paths[offset : offset + self.chunk_size]
            variables = ["$owner:String!", "$name:String!"]
            fields: list[str] = []
            command = ["gh", "api", "graphql"]
            command.extend(["-f", "owner=" + self.owner, "-f", "name=" + self.name])
            for index, path in enumerate(chunk):
                key = f"expr{index}"
                variables.append(f"${key}:String!")
                fields.append(
                    f'b{index}:object(expression:${key}){{... on Blob{{oid text}}}}'
                )
                command.extend(["-f", f"{key}={ref}:{path}"])
            query = (
                "query(" + ",".join(variables) + "){repository(owner:$owner,name:$name){"
                + "".join(fields)
                + "}}"
            )
            command.extend(["-f", "query=" + query])
            value = self._json(command)
            repository = (
                value.get("data", {}).get("repository")
                if isinstance(value, dict)
                else None
            )
            if not isinstance(repository, dict):
                raise SnapshotError("GraphQL snapshot response is missing repository data")
            for index, path in enumerate(chunk):
                blob = repository.get(f"b{index}")
                expected_sha = path_to_sha[path]
                if (
                    not isinstance(blob, dict)
                    or blob.get("oid") != expected_sha
                    or not isinstance(blob.get("text"), str)
                ):
                    raise SnapshotError(
                        f"GraphQL blob mismatch for {path}: expected {expected_sha}"
                    )
                target = self._blob_path(expected_sha)
                temp = target.with_suffix(".tmp")
                temp.write_text(blob["text"], encoding="utf-8")
                temp.replace(target)

    def load(self, ref: str) -> LedgerSnapshot:
        if not SHA_RE.fullmatch(ref):
            raise SnapshotError("Ledger snapshot ref must be a 40-character commit SHA")
        cached = self._memory.get(ref)
        if cached is not None:
            return cached

        path_to_sha = self._tree_index(ref)
        missing = [
            path
            for path, sha in path_to_sha.items()
            if not self._blob_path(sha).is_file()
        ]
        if missing:
            self._fetch_blobs(ref, path_to_sha, missing)

        objects: dict[str, Any] = {}
        for path, sha in path_to_sha.items():
            try:
                text = self._blob_path(sha).read_text(encoding="utf-8")
                objects[path] = json.loads(text)
            except (OSError, json.JSONDecodeError) as exc:
                raise SnapshotError(f"cached Ledger blob is invalid: {path}") from exc
        snapshot = LedgerSnapshot(ref=ref, blob_shas=path_to_sha, objects=objects)
        self._memory[ref] = snapshot
        return snapshot
