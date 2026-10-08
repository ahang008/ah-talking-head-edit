import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/"skills/ah-talking-head-edit/scripts"
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location("independent_pause_audit",SCRIPTS/"pause_audit.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PauseCandidatesTests(unittest.TestCase):
    def test_silence_spanning_join_is_one_candidate(self):
        rows=m.candidates("silence_start: 0.8\nsilence_end: 1.3",2,[1])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["crossed_cuts"],[1])
        self.assertEqual(rows[0]["decision"],"CHECK")
    def test_trailing_low_energy_is_included(self):
        self.assertEqual(m.candidates("silence_start: 1.1",2,[])[0]["end"],2)
    def test_short_low_energy_is_not_auto_cut(self):
        self.assertEqual(m.candidates("silence_start: 0.5\nsilence_end: 0.6",2,[]),[])
    def test_invalid_or_unpaired_events_fail(self):
        with self.assertRaises(ValueError):m.candidates("silence_end: 1",2,[])
        with self.assertRaises(ValueError):m.candidates("",2,[3])
    def test_same_duration_different_master_cannot_reuse_old_evidence(self):
        report={"status":"completed","project_sha256":"p","artifacts":{"video":{"sha256":"old"}}}
        with self.assertRaises(ValueError):m.check_render_hashes(report,"p","new")
    def test_changed_cut_plan_cannot_reuse_master_evidence(self):
        report={"status":"completed","project_sha256":"old","artifacts":{"video":{"sha256":"v"}}}
        with self.assertRaises(ValueError):m.check_render_hashes(report,"new","v")
