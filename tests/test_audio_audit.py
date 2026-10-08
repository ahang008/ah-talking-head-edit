import importlib.util
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"skills/ah-talking-head-edit/scripts/audio_audit.py"
spec=importlib.util.spec_from_file_location("audio_audit",SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def event(start,end,target,audible=True):
    return dict(material="verified-source-hash",source_start=start,source_end=end,timeline_start=target,timeline_end=target+end-start,audible=audible)

class AudioReuseTests(unittest.TestCase):
    def test_layered_embedded_and_detached_audio(self):
        kinds={x["kind"] for x in m.audit([event(0,2,0),event(0,2,0)])["findings"]}
        self.assertEqual(kinds,{"audible_layer_overlap","reused_source_interval"})
    def test_sequential_reuse_is_detected(self):
        self.assertEqual(m.audit([event(0,2,0),event(0,2,2)])["findings"][0]["kind"],"reused_source_interval")
    def test_muted_track_does_not_flag(self):
        self.assertEqual(m.audit([event(0,2,0),event(0,2,0,False)])["findings"],[])
    def test_adjacent_distinct_source_has_no_structural_duplicate(self):
        self.assertEqual(m.audit([event(0,2,0),event(2,4,2)])["findings"],[])
    def test_missing_audible_track_cannot_pass(self):
        e=event(0,2,0);e['track_id']='embedded'
        r=m.audit([e],{'audible_track_ids':['embedded','detached'],'duration_seconds':2})
        self.assertEqual(r['status'],'incomplete_scope')
        self.assertEqual(r['scope_problems'][0]['missing'],['detached'])
    def test_scoped_result_without_inventory_does_not_claim_whole_video(self):
        r=m.audit([event(0,2,0)])
        self.assertEqual(r['status'],'passed_scoped_checks')
        self.assertEqual(r['whole_video_acceptance'],'not_established')
    def test_partial_track_can_be_valid_without_continuous_coverage(self):
        e=event(0,2,1);e['track_id']='embedded'
        r=m.audit([e],{'audible_track_ids':['embedded'],'duration_seconds':5})
        self.assertEqual(r['scope_problems'],[])
        self.assertEqual(r['findings'][0]['kind'],'uncovered_timeline_interval')
    def test_event_exceeding_timeline_is_not_accepted(self):
        e=event(0,2,0);e['track_id']='embedded'
        r=m.audit([e],{'audible_track_ids':['embedded'],'duration_seconds':1})
        self.assertEqual(r['status'],'incomplete_scope')
    def test_other_audible_track_covers_sparse_track_gap(self):
        a=event(0,1,0);a['track_id']='speech'
        b=event(3,4,1);b['track_id']='music'
        r=m.audit([a,b],{'audible_track_ids':['speech','music'],'duration_seconds':2})
        self.assertEqual(r['findings'],[])
    def test_timeline_hole_is_a_review_candidate_not_proven_silence(self):
        a=event(0,1,0);a['track_id']='speech'
        b=event(2,3,2);b['track_id']='speech'
        r=m.audit([a,b],{'audible_track_ids':['speech'],'duration_seconds':3})
        self.assertEqual(r['findings'][0]['start'],1)
        self.assertTrue(r['limits']['event_coverage_is_not_acoustic_silence'])
