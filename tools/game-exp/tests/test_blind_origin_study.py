from __future__ import annotations
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
PATH = ROOT / "plugins/game-exp/skills/game-exp/scripts/blind_origin_study.py"
spec = importlib.util.spec_from_file_location("blind_origin_study", PATH)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)

def fixture():
    h = "sha256:" + "a" * 64
    return {
        "schema_version":1,"study_id":"SYNTHETIC-UNIT","brief_digest":h,
        "baseline_digest":h,"evaluation_profile_digest":h,
        "resource_budget":{"model":"fixed","max_minutes":60,"max_model_calls":10},
        "playtest":{"minimum_seconds_per_version":60,"planned_min_responses":5,
                    "population":"adult testers","recruitment":"convenience",
                    "limitations":"synthetic unit fixture, not consumer evidence"},
        "variants":[{
            "origin":origin,"candidate_id":f"C-{i}-123-1","source_sha":str(i)*40,
            "artifact_digest":"sha256:"+str(i)*64,
            "baseline_digest":h,"design_trace_digest":"sha256:"+str(i+2)*64,
            "evaluation":{"profile_digest":h,"result_digest":"sha256:"+str(i+4)*64,
                          "screening":"ELIGIBLE","source":"TRUSTED_OBSERVED"},
            "delivery_url":f"https://example.org/play/{i}/",
            "usage":{"model":"fixed","minutes":40,"model_calls":7}
        } for i,origin in enumerate(("AI_ONLY","HUMAN_AI"),1)]}

class BlindOriginStudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.plan = fixture()
        self.p = self.root/"plan.json"
        self.secret = self.root/"private"
        self.public = self.root/"pages"

    def prepare(self,n=4):
        self.p.write_text(json.dumps(self.plan),encoding="utf-8")
        study.prepare(self.p,self.secret,self.public,n)
        return study._state(self.secret)

    def vote(self,sid,choice="A_SLIGHTLY_BETTER",played=True):
        row={"schema_version":1,"study_id":self.plan["study_id"],
             "session_id":sid,"choice":choice,"self_reported_played_both":played}
        f=self.root/"response.json"
        f.write_text(json.dumps(row),encoding="utf-8")
        return study.record(self.secret,f)

    def test_no_votes_never_implies_player_preference(self):
        self.prepare()
        r=study.report(self.secret)
        self.assertEqual(r["status"],"NO_OBSERVED_PLAYER_PREFERENCES")
        self.assertEqual(r["recorded_responses"],0)
        self.assertEqual(sum(r["counts_by_operator_declared_origin"].values()),0)

    def test_balanced_order_and_public_blinding(self):
        state=self.prepare(10)
        self.assertEqual(sum(v["order"][0]==0 for v in state["sessions"].values()),5)
        for session in state["sessions"].values():
            page=(self.public/session["public_file"]).read_text(encoding="utf-8")
            for secret in ("AI_ONLY","HUMAN_AI","sha256:","candidate_id"):
                self.assertNotIn(secret,page)
            self.assertIn("版本 A",page)

    def test_synthetic_decoding_and_one_vote_per_session(self):
        state=self.prepare(2)
        for sid,row in state["sessions"].items():
            idx=next(x for x,v in enumerate(row["order"]) if self.plan["variants"][v]["origin"]=="AI_ONLY")
            self.vote(sid,"A_MUCH_BETTER" if idx==0 else "B_MUCH_BETTER")
        result=study.report(self.secret)
        self.assertEqual(result["counts_by_operator_declared_origin"]["AI_ONLY"],2)
        self.assertEqual(result["status"],"DESCRIPTIVE_BELOW_PREDECLARED_MINIMUM")
        with self.assertRaises(FileExistsError):
            self.vote(sid)

    def test_uncertain_is_not_a_win(self):
        state=self.prepare(1)
        sid=next(iter(state["sessions"]))
        self.vote(sid,"INCONCLUSIVE",False)
        self.assertEqual(study.report(self.secret)["counts_by_operator_declared_origin"]["INCONCLUSIVE"],1)

    def test_no_false_report_or_unassigned_vote(self):
        state=self.prepare(1)
        with self.assertRaises(study.StudyError):
            self.vote("not-allocated")
        sid=next(iter(state["sessions"]))
        with self.assertRaises(study.StudyError):
            self.vote(sid,played=False)

    def test_provenance_digest_tampering_fails(self):
        self.prepare(1)
        path=self.secret/"trial.json"
        data=json.loads(path.read_text(encoding="utf-8"))
        sid=next(iter(data["sessions"]))
        data["sessions"][sid]["order"].reverse()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(study.StudyError):
            study.report(self.secret)

    def test_incompatible_profile_rejected(self):
        self.plan["variants"][1]["evaluation"]["profile_digest"]="sha256:"+"f"*64
        with self.assertRaises(study.StudyError):
            self.prepare()

    def test_ineligible_candidate_rejected(self):
        self.plan["variants"][0]["evaluation"]["screening"]="INCONCLUSIVE"
        with self.assertRaises(study.StudyError):
            self.prepare()

    def test_baseline_change_rejected(self):
        self.plan["variants"][1]["baseline_digest"]="sha256:"+"f"*64
        with self.assertRaises(study.StudyError):
            self.prepare()

    def test_mismatched_resources_rejected(self):
        self.plan["variants"][1]["usage"]["model"]="other-model"
        with self.assertRaises(study.StudyError):
            self.prepare()

    def test_shared_limit_is_not_actual_equal_usage(self):
        self.plan["variants"][1]["usage"]["minutes"]=22
        self.prepare()
        self.assertFalse(study.report(self.secret)["actual_reported_resource_usage_equal"])

    def test_source_leaking_url_rejected(self):
        self.plan["variants"][0]["delivery_url"]="https://example.org/human-ai/"
        with self.assertRaises(study.StudyError):
            self.prepare()

    def test_cannot_mix_public_and_private_directories(self):
        self.p.write_text(json.dumps(self.plan), encoding="utf-8")
        with self.assertRaises(study.StudyError):
            study.prepare(self.p,self.secret,self.secret/"pages",2)

if __name__=="__main__":
    unittest.main()
