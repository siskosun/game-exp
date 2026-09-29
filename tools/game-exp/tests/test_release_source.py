from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

TOOLS_DIR = pathlib.Path(__file__).resolve().parents[1]
ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from release_source import (  # noqa: E402
    ReleaseSourceError,
    resolve_install_source,
)


def release_archive(version: str) -> bytes:
    stream = io.BytesIO()
    root = f"game-exp-{version}"
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{root}/VERSION.txt", version + "\n")
        archive.writestr(
            f"{root}/plugins/game-exp/plugin.json",
            json.dumps({"version": version}),
        )
        archive.writestr(
            f"{root}/INSTALL.json",
            json.dumps(
                {
                    "version": version,
                    "source_of_truth": "https://github.com/siskosun/game-exp",
                }
            ),
        )
    return stream.getvalue()


class ReleaseSourceTests(unittest.TestCase):
    def releases(self) -> list[dict[str, object]]:
        return [
            {
                "tag_name": "v1.3.0",
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/siskosun/game-exp/releases/tag/v1.3.0",
            },
            {
                "tag_name": "v1.4.0",
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/siskosun/game-exp/releases/tag/v1.4.0",
            },
            {
                "tag_name": "v1.5.0",
                "draft": False,
                "prerelease": True,
                "html_url": "https://github.com/siskosun/game-exp/releases/tag/v1.5.0",
            },
            {
                "tag_name": "v2.0.0",
                "draft": True,
                "prerelease": False,
                "html_url": "https://github.com/siskosun/game-exp/releases/tag/v2.0.0",
            },
        ]

    def test_stable_defaults_to_latest_published_semver_release(self):
        def request(url: str, *, timeout: int = 30) -> bytes:
            if "/releases?" in url:
                return json.dumps(self.releases()).encode("utf-8")
            if url.endswith("/v1.4.0"):
                return release_archive("1.4.0")
            raise AssertionError(url)

        with mock.patch("release_source._request_bytes", side_effect=request):
            resolved = resolve_install_source(ROOT, channel="stable")
            try:
                self.assertEqual(resolved.channel, "stable")
                self.assertEqual(resolved.ref, "v1.4.0")
                self.assertEqual(resolved.version, "1.4.0")
                self.assertEqual(
                    resolved.release_url,
                    "https://github.com/siskosun/game-exp/releases/tag/v1.4.0",
                )
                self.assertTrue((resolved.root / "VERSION.txt").is_file())
            finally:
                resolved.close()

    def test_explicit_stable_release_can_select_older_published_version(self):
        def request(url: str, *, timeout: int = 30) -> bytes:
            if "/releases?" in url:
                return json.dumps(self.releases()).encode("utf-8")
            if url.endswith("/v1.3.0"):
                return release_archive("1.3.0")
            raise AssertionError(url)

        with mock.patch("release_source._request_bytes", side_effect=request):
            resolved = resolve_install_source(
                ROOT,
                channel="stable",
                release="1.3.0",
            )
            try:
                self.assertEqual(resolved.ref, "v1.3.0")
                self.assertEqual(resolved.version, "1.3.0")
            finally:
                resolved.close()

    def test_prerelease_is_not_selectable_as_stable_release(self):
        with mock.patch(
            "release_source._request_bytes",
            return_value=json.dumps(self.releases()).encode("utf-8"),
        ):
            with self.assertRaisesRegex(
                ReleaseSourceError,
                "published stable Release not found",
            ):
                resolve_install_source(
                    ROOT,
                    channel="stable",
                    release="v1.5.0",
                )

    def test_development_uses_current_checkout_without_network(self):
        with mock.patch("release_source._request_bytes") as request:
            resolved = resolve_install_source(ROOT, channel="development")
            try:
                self.assertEqual(resolved.channel, "development")
                self.assertEqual(resolved.ref, "working-tree")
                self.assertEqual(resolved.root, ROOT.resolve())
            finally:
                resolved.close()
        request.assert_not_called()

    def test_release_is_invalid_with_development_channel(self):
        with self.assertRaisesRegex(
            ReleaseSourceError,
            "cannot be combined",
        ):
            resolve_install_source(
                ROOT,
                channel="development",
                release="v1.3.0",
            )

    def test_release_archive_metadata_must_match_tag(self):
        def request(url: str, *, timeout: int = 30) -> bytes:
            if "/releases?" in url:
                return json.dumps(self.releases()).encode("utf-8")
            if url.endswith("/v1.4.0"):
                return release_archive("1.3.0")
            raise AssertionError(url)

        with mock.patch("release_source._request_bytes", side_effect=request):
            with self.assertRaisesRegex(
                ReleaseSourceError,
                "does not match its tag",
            ):
                resolve_install_source(ROOT, channel="stable")


if __name__ == "__main__":
    unittest.main()
