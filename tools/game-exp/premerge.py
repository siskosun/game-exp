from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
MCP_SPEC = "mcp==2.2.0"


class PremergeError(RuntimeError):
    pass


def run(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "output": proc.stdout,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }


def premerge() -> dict[str, Any]:
    uv = shutil.which("uv")
    if uv is None:
        raise PremergeError("uv is required for the full game-exp premerge check")

    steps = [
        run(
            [
                uv,
                "run",
                "--with",
                MCP_SPEC,
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tools/game-exp/tests",
                "-p",
                "test_*.py",
            ]
        ),
        run(
            [
                sys.executable,
                "tools/game-exp/distribution_check.py",
                "--json",
            ]
        ),
        run(
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                "tools/game-exp",
            ]
        ),
    ]
    return {
        "status": "PASS" if all(row["status"] == "PASS" for row in steps) else "FAIL",
        "root": str(ROOT),
        "mcp_spec": MCP_SPEC,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the game-exp 1.0 premerge gate.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = premerge()
    except PremergeError as exc:
        result = {"status": "FAIL", "error": str(exc)}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result.get('status')}\tgame-exp premerge")
        for row in result.get("steps", []):
            print(
                f"{row['status']}\t{' '.join(row['command'])}\n"
                f"{row['output'].rstrip()}"
            )
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
