import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/ah-talking-head-edit/scripts/captions.py"

class NativeCaptionTests(unittest.TestCase):
    def test_preserves_segmentation_correction_and_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            source = d / "native.srt"
            original = "1\n00:00:00,200 --> 00:00:00,600\n阿航\n\n2\n00:00:01,100 --> 00:00:01,800\n第二句\n\n"
            source.write_text(original)
            changes = d / "changes.json"
            changes.write_text(json.dumps([{"cue":1,"before":"阿航","after":"阿杭"}]))
            output, report = d / "corrected.srt", d / "report.json"
            args = [sys.executable,str(SCRIPT),"prepare","--srt",str(source),"--duration","2.5","--corrections",str(changes),"--output",str(output),"--report",str(report)]
            result = subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(source.read_text(),original)
            self.assertEqual(output.read_text(),"1\n00:00:00,000 --> 00:00:01,100\n阿杭\n\n2\n00:00:01,100 --> 00:00:02,500\n第二句\n\n")
            self.assertEqual(json.loads(report.read_text())["gaps"],[])
            self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
            self.assertEqual(source.read_text(),original)

    def test_mismatched_correction_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            source = d / "native.srt"
            source.write_text("1\n00:00:00,200 --> 00:00:00,600\n原文\n\n")
            changes = d / "changes.json"
            changes.write_text(json.dumps([{"cue":1,"before":"不匹配","after":"修正"}]))
            output, report = d / "out.srt", d / "report.json"
            result = subprocess.run([sys.executable,str(SCRIPT),"prepare","--srt",str(source),"--duration","1","--corrections",str(changes),"--output",str(output),"--report",str(report)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(output.exists())
            self.assertFalse(report.exists())

    def test_native_comparison_rejects_unapproved_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            native = d / 'native.srt'
            native.write_text('1\n00:00:00,200 --> 00:00:00,600\n阿航\n\n2\n00:00:01,100 --> 00:00:01,800\n第二句\n\n')
            changes = d / 'changes.json'
            changes.write_text(json.dumps([{'cue':1,'before':'阿航','after':'阿杭'}]))
            good = '1\n00:00:00,000 --> 00:00:01,100\n阿杭\n\n2\n00:00:01,100 --> 00:00:02,500\n第二句\n\n'
            variants = [good, good.replace('第二句','额外改字'), good.replace('01,100','01,200'), '1\n00:00:00,000 --> 00:00:02,500\n阿杭第二句\n\n']
            for n, text in enumerate(variants):
                final = d / f'final{n}.srt'; final.write_text(text)
                report = d / f'report{n}.json'
                run = subprocess.run([sys.executable,str(SCRIPT),'audit','--srt',str(final),'--native-srt',str(native),'--corrections',str(changes),'--duration','2.5','--report',str(report)],capture_output=True,text=True)
                self.assertEqual(run.returncode, 0 if n == 0 else 1, run.stderr)
                result = json.loads(report.read_text())
                self.assertEqual(result['human_listening'], 'unverified')
                self.assertEqual(result['native_comparison']['status'], 'passed' if n == 0 else 'failed')

if __name__ == "__main__":
    unittest.main()
