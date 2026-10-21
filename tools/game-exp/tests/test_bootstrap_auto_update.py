import hashlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
import zipfile

HERE=pathlib.Path(__file__).resolve()
SCRIPT=HERE.parents[3]/"plugins/game-exp/skills/game-exp/scripts/bootstrap_auto_update.py"
spec=importlib.util.spec_from_file_location("four_skill_bootstrap",SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TAG="v0.4.7"
def archive():
    buf=io.BytesIO()
    files={
        "game-opportunity/SKILL.md":"---\nname: game-opportunity\n---\n",
        "game-opportunity/VERSION":"0.4.7\n",
        "game-opportunity/compatibility.lock.json":"{}",
        "game-opportunity/scripts/auto_update_bundle.py":"#!/usr/bin/env python3\nprint('{}')\n",
    }
    with zipfile.ZipFile(buf,"w") as output:
        for name,content in files.items():output.writestr(name,content)
    return buf.getvalue()
def meta(payload):
    return {"tag_name":TAG,"draft":False,"prerelease":False,
            "assets":[{"name":"skill.zip","digest":"sha256:"+hashlib.sha256(payload).hexdigest(),
                       "browser_download_url":f"https://github.com/siskosun/game-opportunity/releases/download/{TAG}/skill.zip"}]}
class BootstrapTests(unittest.TestCase):
    def test_valid_verified_updater(self):
        payload=archive()
        def fake(url,cap):
            return json.dumps(meta(payload)).encode() if url==mod.META else payload
        self.assertTrue(mod.trusted_updater(get=fake).startswith(b"#!/usr/bin/env python3"))
    def test_digest_mismatch_fails_closed(self):
        payload=archive()
        def fake(url,cap):
            if url==mod.META:
                m=meta(payload);m["assets"][0]["digest"]="sha256:"+"0"*64
                return json.dumps(m).encode()
            return payload
        with self.assertRaisesRegex(mod.BootstrapError,"HASH_MISMATCH"):
            mod.trusted_updater(get=fake)
    def test_prerelease_rejected(self):
        payload=archive()
        def fake(url,cap):
            m=meta(payload);m["prerelease"]=True
            return json.dumps(m).encode()
        with self.assertRaisesRegex(mod.BootstrapError,"NOT_STABLE"):
            mod.trusted_updater(get=fake)
    def test_apply_is_explicit(self):
        payload=archive()
        def fake(url,cap):
            return json.dumps(meta(payload)).encode() if url==mod.META else payload
        seen=[]
        class Result:
            returncode=0
            stdout='{"status":"CURRENT","writes":false}'
        def runner(argv,**kwargs):
            seen.append(argv)
            return Result()
        with tempfile.TemporaryDirectory() as t:
            output=mod.run(harness="codex",home=pathlib.Path(t),apply=False,get=fake,subprocess_run=runner)
            self.assertEqual(output["status"],"CURRENT")
            self.assertNotIn("--apply",seen[-1])
            mod.run(harness="codex",home=pathlib.Path(t),apply=True,get=fake,subprocess_run=runner)
            self.assertIn("--apply",seen[-1])
if __name__=="__main__":unittest.main()
