#!/usr/bin/env python3
"""Fetch the verified game-opportunity stable Release updater and run it.

This is a local, explicitly invoked command, not an automatic Python import
hook. Only siskosun/game-opportunity Release skill.zip is an authorized source.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import pathlib
import re
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

REPO = "siskosun/game-opportunity"
META = "https://api.github.com/repos/" + REPO + "/releases/latest"
SEMVER = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SCRIPT_NAME = "game-opportunity/scripts/auto_update_bundle.py"

class BootstrapError(ValueError):
    pass

def get_bytes(url: str, limit: int) -> bytes:
    if url != META and not (
        url.startswith("https://github.com/" + REPO + "/releases/download/")
        and url.endswith("/skill.zip")
    ):
        raise BootstrapError("UNTRUSTED_URL")
    request = urllib.request.Request(url,headers={"User-Agent":"four-game-skills-bootstrap/1.0"})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:
            data=response.read(limit+1)
    except (OSError,TimeoutError,urllib.error.URLError) as exc:
        raise BootstrapError("RELEASE_UNAVAILABLE") from exc
    if len(data)>limit:
        raise BootstrapError("RELEASE_TOO_LARGE")
    return data

def trusted_updater(*,get=get_bytes) -> bytes:
    try:
        meta=json.loads(get(META,262144))
    except (UnicodeError,ValueError,TypeError) as exc:
        raise BootstrapError("INVALID_RELEASE_METADATA") from exc
    if not isinstance(meta,dict) or meta.get("draft") or meta.get("prerelease"):
        raise BootstrapError("NOT_STABLE_RELEASE")
    tag=meta.get("tag_name")
    if not isinstance(tag,str) or not SEMVER.fullmatch(tag):
        raise BootstrapError("INVALID_RELEASE_TAG")
    assets=meta.get("assets",[])
    if not isinstance(assets,list):
        raise BootstrapError("INVALID_ASSET_LIST")
    asset=next((a for a in assets if isinstance(a,dict) and a.get("name")=="skill.zip"),None)
    url=f"https://github.com/{REPO}/releases/download/{tag}/skill.zip"
    if not asset or asset.get("browser_download_url")!=url or not isinstance(asset.get("digest"),str) or not DIGEST.fullmatch(asset["digest"]):
        raise BootstrapError("INVALID_RELEASE_ASSET")
    payload=get(url,16*1024*1024)
    if hashlib.sha256(payload).hexdigest()!=asset["digest"][7:]:
        raise BootstrapError("ASSET_HASH_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names=archive.namelist()
            if len(names)>4096:
                raise BootstrapError("ARCHIVE_TOO_MANY_FILES")
            for required in ("game-opportunity/SKILL.md","game-opportunity/VERSION",
                             "game-opportunity/compatibility.lock.json",SCRIPT_NAME):
                if required not in names:
                    raise BootstrapError("INCOMPLETE_RELEASE_ARCHIVE")
            marker=archive.read("game-opportunity/VERSION").decode("utf-8").strip()
            if marker != tag.lstrip("v"):
                raise BootstrapError("RELEASE_VERSION_MISMATCH")
            entry=archive.getinfo(SCRIPT_NAME)
            mode=(entry.external_attr >> 16) & 0o170000
            if entry.file_size > 128*1024 or mode not in (0,stat.S_IFREG) or entry.is_dir():
                raise BootstrapError("UNSAFE_UPDATER_FILE")
            raw=archive.read(entry)
    except (OSError,zipfile.BadZipFile,UnicodeError,KeyError) as exc:
        raise BootstrapError("INVALID_RELEASE_ZIP") from exc
    if not raw.startswith(b"#!/usr/bin/env python3\n"):
        raise BootstrapError("INVALID_UPDATER_SCRIPT")
    return raw

def run(*,harness:str,home:pathlib.Path,apply:bool, get=get_bytes,
        subprocess_run=subprocess.run) -> dict:
    script=trusted_updater(get=get)
    with tempfile.TemporaryDirectory(prefix="four-skill-bootstrap-") as temp:
        path=pathlib.Path(temp)/"verified_auto_update_bundle.py"
        path.write_bytes(script)
        args=[sys.executable,str(path),"--harness",harness,"--home",str(home),"--json"]
        if apply: args.append("--apply")
        try:
            proc=subprocess_run(args,capture_output=True,text=True,encoding="utf-8",
                                errors="replace",timeout=420)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise BootstrapError("UPDATER_EXECUTION_FAILED") from exc
        try:
            result=json.loads(proc.stdout)
        except (ValueError,TypeError) as exc:
            raise BootstrapError("INVALID_UPDATER_REPORT") from exc
        if not isinstance(result,dict):
            raise BootstrapError("INVALID_UPDATER_REPORT")
        if proc.returncode:
            return {"status":"UNVERIFIED","reason":"UPDATER_FAILED","updater_status":result.get("status"),
                    "writes":bool(result.get("writes",False))}
        return result

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness",required=True,choices=("codex","cursor","qoder"))
    parser.add_argument("--home",type=pathlib.Path,default=pathlib.Path.home())
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=run(harness=args.harness,home=args.home.expanduser().resolve(),apply=args.apply)
    except (ValueError,OSError,zipfile.BadZipFile) as exc:
        result={"status":"UNVERIFIED","reason":str(exc) if isinstance(exc,BootstrapError) else type(exc).__name__,"writes":False}
    print(json.dumps(result,ensure_ascii=False,indent=2) if args.json else result["status"])
    return 0 if result.get("status") in ("CURRENT","UPDATE_AVAILABLE","UPDATED") else 2

if __name__=="__main__":
    raise SystemExit(main())
