import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location("review_audit",Path(__file__).resolve().parents[1]/"skills/ah-talking-head-edit/scripts/review_audit.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def packet():
    pause={"status":"candidates_only","video_sha256":"v","project_sha256":"p","candidates":[{}]}
    review={"video_sha256":"v","project_sha256":"p","pause_report_sha256":"r",
            "decisions":[{"candidate":1,"decision":"KEEP","reason":"natural pause","reviewer":"user","listening_evidence":"listened to 0-2s"}],
            "stages":{k:{"status":"verified","reviewer":"user","evidence":"recorded scope"} for k in m.STAGES}}
    return pause,review

class ReviewGateTests(unittest.TestCase):
    def test_missing_candidate_cannot_pass(self):
        p,r=packet();r['decisions']=[]
        self.assertEqual(m.audit(p,r,'v','p','r')['status'],'needs_review')
    def test_planned_delete_requires_rerender(self):
        p,r=packet();r['decisions'][0]['decision']='DELETE'
        self.assertEqual(m.audit(p,r,'v','p','r')['status'],'needs_review')
    def test_changed_master_invalidates_old_review_even_same_duration(self):
        p,r=packet()
        self.assertEqual(m.audit(p,r,'changed','p','r')['problems'][0]['kind'],'stale_version')
    def test_missing_listening_and_native_evidence_stay_pending(self):
        p,r=packet();del r['stages']['full_listening']
        stages={x.get('stage') for x in m.audit(p,r,'v','p','r',native=True)['problems']}
        self.assertIn('full_listening',stages);self.assertIn('native_persistence',stages)
    def test_duplicate_decision_does_not_hide_missing_candidate(self):
        p,r=packet();r['decisions']*=2
        with self.assertRaises(ValueError):m.audit(p,r,'v','p','r')
    def test_complete_records_do_not_claim_script_listened(self):
        p,r=packet();out=m.audit(p,r,'v','p','r')
        self.assertEqual(out['status'],'review_records_complete')
        self.assertFalse(out['limits']['listening_performed_by_script'])
