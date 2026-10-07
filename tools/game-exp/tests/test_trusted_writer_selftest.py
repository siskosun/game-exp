from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(os.name == "posix" and shutil.which("bash") and shutil.which("git"),
                     "the Actions protocol script requires Bash and Git")
class TrustedWriterSelftestTests(unittest.TestCase):
    def test_workflow_protocol_cases_against_real_writer_and_local_git(self):
        workflow = (ROOT / ".github/workflows/game-exp-trusted-writer-selftest.yml").read_text()
        step = workflow.split("      - name: Run five protocol cases\n", 1)[1]
        script = step.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
        script = "\n".join(line[10:] for line in script.splitlines())

        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            remote = work / "remote.git"
            env = os.environ.copy()
            config = work / "gitconfig"
            config.write_text(
                '[user]\n name = Local selftest\n email = local@example.invalid\n'
                '[commit]\n gpgsign = false\n'
                f'[url "{remote.as_uri()}"]\n'
                ' insteadOf = git@github.com:local/selftest.git\n'
                ' insteadOf = https://github.com/local/selftest.git\n'
            )
            env.update({"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_TERMINAL_PROMPT": "0"})

            def git(*args):
                return subprocess.run(["git", *args], cwd=work, env=env, text=True,
                                      capture_output=True, check=True).stdout.strip()

            git("init", "--bare", str(remote))
            git("clone", str(remote), "seed")
            git("-C", "seed", "checkout", "-b", "game-exp/ledger")
            (work / "seed/seed.json").write_text("{}\n")
            git("-C", "seed", "add", ".")
            git("-C", "seed", "commit", "-m", "Local Ledger seed")
            git("-C", "seed", "push", "origin", "HEAD:game-exp/ledger")
            seed_head = git("-C", "seed", "rev-parse", "HEAD")
            control = work / "control/tools/game-exp"
            control.mkdir(parents=True)
            for name in ("trusted_writer.py", "protocol_core.py", "domain_core.py"):
                shutil.copyfile(ROOT / "tools/game-exp" / name, control / name)
            runner_temp = work / "runner-temp"
            runner_temp.mkdir()
            env.update({"GITHUB_REPOSITORY": "local/selftest", "GITHUB_RUN_ID": "local-test",
                        "GITHUB_RUN_ATTEMPT": "1", "WORKFLOW_SOURCE_SHA": "a" * 40,
                        "GAME_EXP_WRITER_KEY_PATH": str(work / "unused-key"),
                        "RUNNER_TEMP": str(runner_temp)})
            result = subprocess.run(["bash", "-c", script], cwd=work, env=env,
                                    text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            def evidence(name):
                return json.loads((work / "evidence" / name).read_text())

            normal = evidence("normal.json")
            replay = evidence("idempotent.json")
            self.assertEqual(normal["ledger_head"], replay["ledger_head"])
            self.assertEqual(evidence("request-conflict.json")["ledger_head"], normal["ledger_head"])
            record = evidence("stale-head-record.json")
            self.assertEqual(record["expected_head"], seed_head)
            self.assertEqual(record["writer_base_head"], normal["ledger_head"])
            lost = evidence("lost-response-retry.json")
            self.assertEqual(lost["ledger_head"], git("--git-dir", str(remote), "rev-parse", "game-exp/ledger"))
            operations = git("--git-dir", str(remote), "ls-tree", "--name-only",
                             "game-exp/ledger:operations").splitlines()
            self.assertEqual(len(operations), 3)


if __name__ == "__main__":
    unittest.main()
