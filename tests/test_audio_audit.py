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
