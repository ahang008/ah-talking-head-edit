import importlib.util
import json
from pathlib import Path
import sys
import struct
import tempfile
import unittest
import wave

scripts=Path(__file__).resolve().parents[1]/'skills/ah-talking-head-edit/scripts'
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location('listening_pack',scripts/'listening_pack.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ListeningPackTests(unittest.TestCase):
    def test_edge_context_stays_inside_source(self):
        self.assertEqual(m.window(0.1,2,10),[0,2.1])
        self.assertEqual(m.window(9.5,2,10),[7.5,10])
    def test_cross_cut_priority_preserves_unexported_ids(self):
        rows=[dict(crossed_cuts=[],explicit_reason_required=True,seconds=2),dict(crossed_cuts=[1],explicit_reason_required=False,seconds=.3)]
        chosen,left=m.shortlist(rows,1)
        self.assertEqual(chosen[0][0],2);self.assertEqual(left,[1])
    def test_invalid_window_and_limit_do_not_export(self):
        with self.assertRaises(ValueError):m.window(11,2,10)
        with self.assertRaises(ValueError):m.shortlist([],0)
    def test_export_preserves_channels_level_and_window_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.wav';output=Path(temp)/'sample.wav'
            with wave.open(str(source),'wb') as f:
                f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000)
                f.writeframes(struct.pack('<hh',2000,-1000)*96000)
            m.extract(source,0,[.25,1.25],output)
            with wave.open(str(output),'rb') as f:
                self.assertEqual(f.getnchannels(),2)
                self.assertEqual(f.getnframes(),48000)
                self.assertEqual(struct.unpack('<hh',f.readframes(1)),(2000,-1000))
    def test_stale_pack_cannot_be_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            (directory/'listening-index.json').write_text(json.dumps({'video_sha256':'old','items':[]}))
            with self.assertRaises(ValueError):m.verify_pack(directory,{'video_sha256':'new'})
    def test_modified_sample_cannot_be_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);sample=directory/'sample.wav';sample.write_bytes(b'original')
            entry={'file':'sample.wav','sha256':m.digest(sample)}
            (directory/'listening-index.json').write_text(json.dumps({'video_sha256':'v','items':[{'edited':entry,'source_contexts':[]}]}))
            sample.write_bytes(b'changed')
            with self.assertRaises(ValueError):m.verify_pack(directory,{'video_sha256':'v'})
