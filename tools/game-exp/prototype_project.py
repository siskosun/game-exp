from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any

from bootstrap import Bootstrapper
from companion_skills import (
    COMPANION_SKILLS,
    _latest_semver_tag,
    _request_bytes,
    _safe_extract,
    _validate_skill,
)
from project_setup import ProjectSetupError, provision as project_provision

REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
STACKS = {"godot", "h5"}
VISIBILITIES = {"private", "public"}
H5_MODES = {"probe", "slice"}


class PrototypeProjectError(RuntimeError):
    pass


def _run(
    args: list[str],
    *,
    cwd: pathlib.Path | None = None,
    check: bool = True,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd is not None else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise PrototypeProjectError(f"required command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PrototypeProjectError(f"command timed out: {' '.join(args[:4])}") from exc
    if check and proc.returncode != 0:
        raise PrototypeProjectError(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def _validate_name(value: str, label: str) -> str:
    value = value.strip()
    if not REPO_NAME_RE.fullmatch(value) or value in {".", ".."}:
        raise PrototypeProjectError(
            f"{label} must contain only letters, digits, dot, underscore, or hyphen"
        )
    return value


def _authenticated_user() -> dict[str, Any]:
    proc = _run(["gh", "api", "user"])
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise PrototypeProjectError("gh api user returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise PrototypeProjectError("gh api user returned an unexpected payload")
    login = value.get("login")
    user_id = value.get("id")
    if not isinstance(login, str) or not login:
        raise PrototypeProjectError("cannot resolve authenticated GitHub login")
    if not isinstance(user_id, int):
        raise PrototypeProjectError("cannot resolve authenticated GitHub user id")
    return {"login": login, "id": user_id}


def _repo_exists(repo: str) -> bool:
    proc = _run(
        ["gh", "repo", "view", repo, "--json", "nameWithOwner"],
        check=False,
        timeout=30,
    )
    return proc.returncode == 0


def _companion_spec(name: str):
    return next(spec for spec in COMPANION_SKILLS if spec.name == name)


def _materialize_template(
    *,
    stack: str,
    h5_mode: str,
    destination: pathlib.Path,
) -> dict[str, str]:
    if stack == "h5":
        spec = _companion_spec("h5-game-prototype-agent")
        template_rel = "templates/probe" if h5_mode == "probe" else "templates/dom"
    else:
        spec = _companion_spec("godot-prototype-studio")
        template_rel = "assets/starter-2d"

    tag = _latest_semver_tag(spec.repository)
    archive_url = f"https://codeload.github.com/{spec.repository}/zip/refs/tags/{tag}"
    with tempfile.TemporaryDirectory(prefix="game-exp-project-template-") as td:
        temp = pathlib.Path(td)
        archive_path = temp / "source.zip"
        archive_path.write_bytes(_request_bytes(archive_url, timeout=60))
        extract_root = temp / "extract"
        extract_root.mkdir()
        source = _safe_extract(archive_path, extract_root)
        version = _validate_skill(source, spec, tag)
        template = source / pathlib.PurePosixPath(template_rel)
        if not template.is_dir():
            raise PrototypeProjectError(
                f"{spec.repository}@{tag} is missing template {template_rel}"
            )
        shutil.copytree(template, destination)

    return {
        "skill": spec.name,
        "repository": f"https://github.com/{spec.repository}",
        "tag": tag,
        "version": version,
        "template": template_rel,
    }


def _write_gitignore(root: pathlib.Path, stack: str) -> None:
    common = [".DS_Store", "*.log", "*.tmp"]
    if stack == "h5":
        rows = ["node_modules/", "dist/", ".probe/", *common]
    else:
        rows = [".godot/", "dist-godot/", "export/", *common]
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    merged = list(dict.fromkeys([*existing, *rows]))
    path.write_text("\n".join(merged) + "\n", encoding="utf-8")


def _write_godot_policy(root: pathlib.Path) -> None:
    checker = root / "tools" / "prototype_ci.py"
    checker.parent.mkdir(parents=True, exist_ok=True)
    checker.write_text(
        '''from __future__ import annotations

import argparse
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED = [
    "project.godot",
    "scenes/main.tscn",
    "scripts/main.gd",
    "scripts/game_model.gd",
    "qa/qa_bridge.gd",
]


def check() -> None:
    missing = [rel for rel in REQUIRED if not (ROOT / rel).is_file()]
    if missing:
        raise SystemExit("missing required Godot starter files: " + ", ".join(missing))
    project = (ROOT / "project.godot").read_text(encoding="utf-8")
    if 'run/main_scene="res://scenes/main.tscn"' not in project:
        raise SystemExit("project.godot main scene drifted")


def build() -> None:
    check()
    out = ROOT / "dist-godot"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    shutil.copy2(ROOT / "project.godot", out / "project.godot")
    for name in ("scenes", "scripts", "qa"):
        shutil.copytree(ROOT / name, out / name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["check", "build"])
    args = parser.parse_args()
    if args.command == "check":
        check()
    else:
        build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )
    policy = {
        "schema_version": 2,
        "adapter": "godot-source",
        "toolchain": {},
        "install": {"argv": ["python", "tools/prototype_ci.py", "check"]},
        "test": {"argv": ["python", "tools/prototype_ci.py", "check"]},
        "build": {"argv": ["python", "tools/prototype_ci.py", "build"]},
        "candidate": {
            "include": ["dist-godot"],
            "required_paths": [
                "dist-godot/project.godot",
                "dist-godot/scenes/main.tscn",
            ],
        },
    }
    policy_path = root / ".game-exp" / "project-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _configure_git_identity(root: pathlib.Path, user: dict[str, Any]) -> None:
    login = user["login"]
    email = f"{user['id']}+{login}@users.noreply.github.com"
    _run(["git", "config", "user.name", login], cwd=root)
    _run(["git", "config", "user.email", email], cwd=root)
    _run(["git", "config", "core.autocrlf", "false"], cwd=root)


def _repository_url(repo: str) -> str:
    return f"https://github.com/{repo}"


def create_project(
    *,
    name: str,
    stack: str,
    visibility: str = "private",
    owner: str | None = None,
    directory: str | None = None,
    h5_mode: str = "probe",
    description: str | None = None,
    trust_mode: str = "auto",
    run_selftest: bool = True,
) -> dict[str, Any]:
    name = _validate_name(name, "name")
    stack = stack.strip().lower()
    visibility = visibility.strip().lower()
    h5_mode = h5_mode.strip().lower()
    if stack not in STACKS:
        raise PrototypeProjectError("stack must be godot or h5")
    if visibility not in VISIBILITIES:
        raise PrototypeProjectError("visibility must be private or public")
    if h5_mode not in H5_MODES:
        raise PrototypeProjectError("h5_mode must be probe or slice")

    if shutil.which("gh") is None:
        raise PrototypeProjectError("GitHub CLI (gh) is required for project-create")
    if shutil.which("git") is None:
        raise PrototypeProjectError("git is required for project-create")
    if stack == "h5" and shutil.which("node") is None:
        raise PrototypeProjectError("Node.js is required to create an H5 project")

    user = _authenticated_user()
    owner = _validate_name(owner or user["login"], "owner")
    repo = f"{owner}/{name}"
    if _repo_exists(repo):
        raise PrototypeProjectError(
            f"repository already exists: {repo}; use project-init/onboarding instead"
        )

    root = pathlib.Path(directory).expanduser() if directory else pathlib.Path.cwd() / name
    root = root.resolve()
    if root.exists():
        raise PrototypeProjectError(
            f"local project directory already exists: {root}; refusing to overwrite"
        )

    source_root = pathlib.Path(__file__).resolve().parents[2]
    template_info: dict[str, str] | None = None
    repo_created = False
    try:
        template_info = _materialize_template(
            stack=stack,
            h5_mode=h5_mode,
            destination=root,
        )
        _write_gitignore(root, stack)
        if stack == "godot":
            _write_godot_policy(root)

        _run(["git", "init", "-b", "main"], cwd=root)
        _configure_git_identity(root, user)

        Bootstrapper(source_root, root, repo).install()

        metadata = {
            "schema_version": 1,
            "kind": "game-exp-prototype-project",
            "stack": stack,
            "h5_mode": h5_mode if stack == "h5" else None,
            "template": template_info,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "authority": "informational-only",
        }
        meta_path = root / ".game-exp" / "prototype-project.json"
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        _run(["git", "add", "-A"], cwd=root)
        _run(
            ["git", "commit", "-m", f"Initialize {stack} prototype with game-exp"],
            cwd=root,
        )

        command = [
            "gh",
            "repo",
            "create",
            repo,
            f"--{visibility}",
            "--source",
            str(root),
            "--remote",
            "origin",
            "--push",
        ]
        if description:
            command.extend(["--description", description])
        try:
            _run(command, cwd=root, timeout=180)
            repo_created = True
        except PrototypeProjectError as exc:
            if _repo_exists(repo):
                repo_created = True
                return {
                    "status": "INCOMPLETE",
                    "complete": False,
                    "project_readiness": "INCOMPLETE",
                    "repo": repo,
                    "repository_url": _repository_url(repo),
                    "local_path": str(root),
                    "visibility": visibility,
                    "stack": stack,
                    "h5_mode": h5_mode if stack == "h5" else None,
                    "template": template_info,
                    "repo_created": True,
                    "code": "REPOSITORY_PUSH_INCOMPLETE",
                    "error": str(exc),
                    "next_step": "REPAIR_REMOTE_PUSH_THEN_PROJECT_INIT",
                    "next_prompt_zh": (
                        "GitHub 仓库已经存在，但初始推送没有完整确认。"
                        "先修复远端推送并确认 main 包含初始化提交，再运行 project-init；"
                        "不要重新创建仓库。"
                    ),
                }
            raise

        setup = project_provision(
            repo,
            run_selftest=run_selftest,
            trust_mode=trust_mode,
        )
        if not run_selftest and setup.get("status") == "PASS":
            setup = {
                **setup,
                "status": "INCOMPLETE",
                "complete": False,
                "reason": "Trusted Writer self-test was skipped",
            }
        ready = setup.get("status") == "PASS" and setup.get("complete") is True
        return {
            "status": "PASS" if ready else setup.get("status", "INCOMPLETE"),
            "complete": ready,
            "project_readiness": "PROJECT_READY" if ready else "INCOMPLETE",
            "repo": repo,
            "repository_url": _repository_url(repo),
            "local_path": str(root),
            "visibility": visibility,
            "stack": stack,
            "h5_mode": h5_mode if stack == "h5" else None,
            "template": template_info,
            "repo_created": True,
            "setup": setup,
            "next_step": (
                "DESCRIBE_FIRST_EXPERIMENT"
                if ready
                else "RESOLVE_PROJECT_SETUP_BLOCKER"
            ),
            "next_prompt_zh": (
                "仓库已经准备好。现在直接描述第一版想验证的玩法变化和希望玩家产生的体验即可。"
                if ready
                else "仓库已经创建，但 game-exp 信任控制尚未完整。先处理 setup.blockers 后重新运行 project-init；不会自动删除仓库或改成公开。"
            ),
        }
    except ProjectSetupError as exc:
        if repo_created:
            return {
                "status": "INCOMPLETE",
                "complete": False,
                "project_readiness": "INCOMPLETE",
                "repo": repo,
                "repository_url": _repository_url(repo),
                "local_path": str(root),
                "visibility": visibility,
                "stack": stack,
                "h5_mode": h5_mode if stack == "h5" else None,
                "template": template_info,
                "repo_created": True,
                "code": "PROJECT_SETUP_FAILED",
                "error": str(exc),
                "next_step": "RETRY_PROJECT_INIT",
                "next_prompt_zh": (
                    "仓库和源码已经保留。修复权限、套餐或仓库配置后重新运行 project-init；"
                    "不要重新创建仓库，也不要自动改变可见性。"
                ),
            }
        raise PrototypeProjectError(str(exc)) from exc
    except Exception:
        if not repo_created and root.exists():
            shutil.rmtree(root, ignore_errors=True)
        raise
