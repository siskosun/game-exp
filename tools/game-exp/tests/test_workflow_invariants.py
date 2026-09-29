from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
SHA_PIN_RE = re.compile(r"^[^\s@]+@([0-9a-f]{40})$")
USES_RE = re.compile(r"\buses:\s*([^\s#]+)")
JOB_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")


def workflow_files() -> list[pathlib.Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml"))


def job_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    try:
        jobs_index = next(i for i, line in enumerate(lines) if line == "jobs:")
    except StopIteration:
        return {}

    starts: list[tuple[int, str]] = []
    for i in range(jobs_index + 1, len(lines)):
        match = JOB_RE.match(lines[i])
        if match:
            starts.append((i, match.group(1)))

    blocks: dict[str, str] = {}
    for idx, (start, name) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        blocks[name] = "\n".join(lines[start:end])
    return blocks


class WorkflowInvariantTests(unittest.TestCase):
    def test_all_external_actions_are_full_sha_pinned(self):
        files = workflow_files()
        self.assertGreaterEqual(len(files), 16)
        violations: list[str] = []
        for path in files:
            for line_no, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                match = USES_RE.search(line)
                if not match:
                    continue
                target = match.group(1)
                if target.startswith("./") or target.startswith("docker://"):
                    continue
                if SHA_PIN_RE.fullmatch(target) is None:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{line_no}: {target}"
                    )
        self.assertEqual(
            violations,
            [],
            "all external GitHub Actions uses must be pinned to a 40-char commit SHA",
        )

    def test_writer_secret_only_appears_in_protected_environment_jobs(self):
        violations: list[str] = []
        seen = 0
        for path in workflow_files():
            blocks = job_blocks(path.read_text(encoding="utf-8"))
            for job_name, block in blocks.items():
                if "secrets.GAME_EXP_WRITER_KEY" not in block:
                    continue
                seen += 1
                if not re.search(
                    r"^    environment:\s*game-exp-trusted-writer\s*$",
                    block,
                    re.MULTILINE,
                ):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{job_name}"
                    )
        self.assertGreater(seen, 0)
        self.assertEqual(
            violations,
            [],
            "GAME_EXP_WRITER_KEY must only be referenced by an Environment-protected job",
        )

    def test_github_bridge_keeps_untrusted_comment_boundary(self):
        path = WORKFLOW_DIR / "game-exp-github-bridge.yml"
        text = path.read_text(encoding="utf-8")
        blocks = job_blocks(text)

        self.assertIn("issue_comment:", text)
        self.assertIn("author_association", text)
        self.assertIn('["OWNER","MEMBER","COLLABORATOR"]', text)
        self.assertIn("validate", blocks)
        self.assertIn("execute", blocks)

        validate = blocks["validate"]
        execute = blocks["execute"]
        self.assertNotIn("secrets.GAME_EXP_WRITER_KEY", validate)
        self.assertNotRegex(
            validate,
            r"^    environment:\s*game-exp-trusted-writer\s*$",
        )
        self.assertRegex(
            execute,
            r"^    environment:\s*game-exp-trusted-writer\s*$",
        )
        self.assertIn("secrets.GAME_EXP_WRITER_KEY", execute)

        for block in (validate, execute):
            self.assertIn("ref: ${{ github.workflow_sha }}", block)
            self.assertIn("persist-credentials: false", block)

    def test_trusted_writer_selftest_keeps_environment_protection(self):
        path = WORKFLOW_DIR / "game-exp-trusted-writer-selftest.yml"
        blocks = job_blocks(path.read_text(encoding="utf-8"))
        protected = [
            (name, block)
            for name, block in blocks.items()
            if "secrets.GAME_EXP_WRITER_KEY" in block
        ]
        self.assertEqual(len(protected), 1)
        _name, block = protected[0]
        self.assertRegex(
            block,
            r"^    environment:\s*game-exp-trusted-writer\s*$",
        )
        self.assertIn("persist-credentials: false", block)


if __name__ == "__main__":
    unittest.main()
