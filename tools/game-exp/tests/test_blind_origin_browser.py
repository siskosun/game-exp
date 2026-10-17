"""Playwright HTTPS browser smoke test for synthetic, non-human game variants.

Opt-in via GAME_EXP_BROWSER_E2E=1. Core unit runners without Playwright skip
this file; the dedicated browser workflow installs and runs it.
No ledger writes, external service, human respondent or real game is involved.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import importlib.util
import json
import os
import pathlib
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "plugins/game-exp/skills/game-exp/scripts/blind_origin_study.py"
EXAMPLE = ROOT / "examples/blind-origin-synthetic-plan.json"
ENABLED = os.environ.get("GAME_EXP_BROWSER_E2E") == "1"


class SilentStaticHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@unittest.skipUnless(ENABLED, "requires dedicated Playwright HTTPS browser runner")
class BlindOriginHTTPSBrowserTests(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright

        self.temp = tempfile.TemporaryDirectory(prefix="blind-origin-browser-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.host_root = self.root / "host"
        self.host_root.mkdir()
        self.private = self.root / "private"
        self.pages = self.host_root / "pages"
        self.plan_path = self.root / "plan.json"

        for i in (1, 2):
            folder = self.host_root / "games" / str(i)
            folder.mkdir(parents=True)
            # Small playable control, deliberately neutral about creative origin.
            (folder / "index.html").write_text(
                "<!doctype html><html><meta charset='utf-8'>"
                f"<title>Game {i}</title><body><button id='play'>Play</button>"
                "<output id='score'>0</output><script>"
                "document.getElementById('play').onclick=()=>{"
                "document.getElementById('score').textContent='1'}"
                "</script></body></html>",
                encoding="utf-8",
            )

        cert = self.root / "cert.pem"
        key = self.root / "key.pem"
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-nodes", "-days", "1", "-keyout", str(key), "-out", str(cert),
                "-subj", "/CN=localhost",
                "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        self.servers = []
        for _ in range(2):
            handler = functools.partial(SilentStaticHandler, directory=str(self.host_root))
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(cert), str(key))
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.servers.append((server, thread))
        self.addCleanup(self.stop_servers)
        playable_port, public_port = [s.server_address[1] for s, _ in self.servers]
        self.public_host = f"https://127.0.0.1:{public_port}"
        game_host = f"https://127.0.0.1:{playable_port}"

        plan = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(plan["study_id"], "SYNTHETIC-DEMO-NOT-REAL")
        for i, variant in enumerate(plan["variants"], start=1):
            variant["delivery_url"] = f"{game_host}/games/{i}/index.html"
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")

        prep = self.cli(
            "prepare", "--plan", str(self.plan_path),
            "--private-dir", str(self.private),
            "--public-dir", str(self.pages), "--sessions", "2",
        )
        self.assertEqual(prep.returncode, 0, prep.stdout + prep.stderr)
        self.assertEqual(json.loads(prep.stdout)["status"], "PREPARED_NO_RESPONSES")
        self.state = json.loads((self.private / "trial.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {tuple(row["order"]) for row in self.state["sessions"].values()},
            {(0, 1), (1, 0)},
        )

        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)

    def stop_servers(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            check=False,
        )

    def test_mobile_desktop_real_https_iframes_and_downloaded_votes(self):
        initial = self.cli("report", "--private-dir", str(self.private),
                           "--public-dir", str(self.pages))
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        self.assertEqual(json.loads(initial.stdout)["status"], "NO_OBSERVED_PLAYER_PREFERENCES")

        for index, (sid, session) in enumerate(self.state["sessions"].items()):
            context = self.browser.new_context(
                ignore_https_errors=True, accept_downloads=True,
                viewport={"width": 390 if index else 1280, "height": 844 if index else 900},
                is_mobile=bool(index), has_touch=bool(index),
            )
            try:
                page = context.new_page()
                page.goto(f"{self.public_host}/pages/{session['public_file']}", wait_until="load")
                markup = page.content()
                for origin_clue in ("AI_ONLY", "HUMAN_AI", "candidate_id", "sha256:"):
                    self.assertNotIn(origin_clue, markup)
                self.assertFalse(page.locator("#version-B").is_visible())
                self.assertFalse(page.locator("#vote").is_visible())

                # The playable is cross-origin relative to the host page.
                a_game = page.frame_locator('iframe[title="版本 A"]')
                a_game.locator("#play").click(timeout=20000)
                self.assertEqual(a_game.locator("#score").inner_text(), "1")

                page.locator("#next-version").click()
                self.assertFalse(page.locator("#version-A").is_visible())
                self.assertTrue(page.locator("#version-B").is_visible())
                self.assertTrue(page.locator("#vote").is_visible())

                b_game = page.frame_locator('iframe[title="版本 B"]')
                b_game.locator("#play").click(timeout=20000)
                self.assertEqual(b_game.locator("#score").inner_text(), "1")
                page.locator('input[value="B_SLIGHTLY_BETTER"]').check()

                # The form blocks non-eligible vote before both-play confirmation.
                page.locator('#vote button[type="submit"]').click()
                self.assertIn("请先选择结果", page.locator("#message").inner_text())
                page.locator("#played").check()

                with page.expect_download(timeout=20000) as download_event:
                    page.locator('#vote button[type="submit"]').click()
                download = download_event.value
                expected_file = f"vote-{sid}.json"
                self.assertEqual(download.suggested_filename, expected_file)
                saved_path = self.root / expected_file
                download.save_as(saved_path)
                vote = json.loads(saved_path.read_text(encoding="utf-8"))
                self.assertEqual(vote["session_id"], sid)
                self.assertEqual(vote["study_id"], "SYNTHETIC-DEMO-NOT-REAL")
                self.assertEqual(vote["choice"], "B_SLIGHTLY_BETTER")
                self.assertTrue(vote["self_reported_played_both"])

                recorded = self.cli("record", "--private-dir", str(self.private),
                                    "--response", str(saved_path))
                self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
                self.assertEqual(json.loads(recorded.stdout)["status"], "RECORDED_UNVERIFIED")
                duplicate = self.cli("record", "--private-dir", str(self.private),
                                     "--response", str(saved_path))
                self.assertEqual(duplicate.returncode, 2)
            finally:
                context.close()

        summary = self.cli("report", "--private-dir", str(self.private),
                           "--public-dir", str(self.pages))
        self.assertEqual(summary.returncode, 0, summary.stdout + summary.stderr)
        result = json.loads(summary.stdout)
        self.assertEqual(result["recorded_responses"], 2)
        self.assertEqual(result["paired_play_reports"], 2)
        self.assertEqual(result["counts_by_operator_declared_origin"]["AI_ONLY"], 1)
        self.assertEqual(result["counts_by_operator_declared_origin"]["HUMAN_AI"], 1)
        self.assertEqual(result["status"], "DESCRIPTIVE_BELOW_PREDECLARED_MINIMUM")
        self.assertTrue(result["public_pages_verified"])

        # Client-visible bytes cannot drift unnoticed after distribution.
        first_page = next(iter(self.state["sessions"].values()))["public_file"]
        page_path = self.pages / first_page
        page_path.write_bytes(page_path.read_bytes() + b"\n<!-- test tamper -->")
        tampered = self.cli("report", "--private-dir", str(self.private),
                            "--public-dir", str(self.pages))
        self.assertEqual(tampered.returncode, 2)
        self.assertIn("public playtest page missing or digest mismatch", tampered.stdout)


if __name__ == "__main__":
    unittest.main()
