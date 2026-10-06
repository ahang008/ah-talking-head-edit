"""Outcome-oriented tests for the new independent editor only.

All test media/output lives under evidence/core-tests. No old engine, native
draft, source capture, Skill, schema or template is opened by these tests.
"""

import importlib.util
import json
import math
import subprocess
import struct
import sys
import unittest
import uuid
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/ah-talking-head-edit/scripts/clip.py"
SPEC = importlib.util.spec_from_file_location("independent_clip", SCRIPT)
clip = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clip)


class IndependentEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_dir = ROOT / "evidence/core-tests" / ("run-" + uuid.uuid4().hex)
        cls.run_dir.mkdir(parents=True)
        cls.source = cls.run_dir / "中文 源视频.mp4"
        arguments = [clip.FFMPEG, "-hide_banner", "-v", "error", "-n",
                     "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30:duration=6",
                     "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=6",
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                     "-shortest", str(cls.source)]
        result = subprocess.run(arguments, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.media = clip.probe(cls.source)
        cls.srt = cls.run_dir / "中文 源字幕.srt"
        cls.srt.write_text("1\n00:00:00,200 --> 00:00:00,600\n第一句 中文。\n\n"
                           "2\n00:00:01,100 --> 00:00:01,800\n第二句完整。\n\n"
                           "3\n00:00:02,100 --> 00:00:02,900\n第三句完整。\n\n"
                           "4\n00:00:04,100 --> 00:00:05,800\n第四句完整。\n\n", encoding="utf-8")
        cls.cues = clip.parse_srt(cls.srt, cls.media["video_duration_seconds"])

    def selection(self, start=0, end=1, speed=1, **extra):
        result = {"source_start": start, "source_end": end, "speed": speed,
                  "decision": "保留用户明确选择的完整表达"}
        result.update(extra)
        return result

    def paths(self, name):
        directory = self.run_dir / (name + "-" + uuid.uuid4().hex[:8])
        directory.mkdir()
        return directory, directory / "计划.json", directory / "可编辑项目.json"

    def cli(self, *arguments, success=True):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, arguments)],
                                capture_output=True, text=True, encoding="utf-8")
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return json.loads(result.stderr)

    def make_project(self, name, selections, source=None, srt=None):
        directory, plan, project = self.paths(name)
        plan.write_text(json.dumps({"clips": selections}, ensure_ascii=False), encoding="utf-8")
        arguments = ["create", "--source", source or self.source, "--plan", plan, "--project", project]
        if srt:
            arguments += ["--srt", srt]
        result = self.cli(*arguments)
        return directory, project, result

    def assert_plan_rejected(self, selections, message):
        with self.assertRaises(clip.EditError) as error:
            clip.compile_plan(selections, [], self.media)
        self.assertIn(message, str(error.exception))

    def test_overlapping_selection_cannot_be_created(self):
        self.assert_plan_rejected([self.selection(0, 2), self.selection(1, 3)], "overlaps")

    def test_out_of_order_selection_cannot_be_created(self):
        self.assert_plan_rejected([self.selection(3, 4), self.selection(0, 1)], "unordered")

    def test_source_bounds_use_actual_video_duration(self):
        self.assert_plan_rejected([self.selection(0, 6.1)], "actual video duration")

    def test_long_audio_tail_does_not_authorize_missing_video(self):
        directory, plan, project = self.paths("audio-longer-than-video")
        source = directory / "video3 audio6.mkv"
        arguments = [clip.FFMPEG, "-hide_banner", "-v", "error", "-n",
                     "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30:duration=3",
                     "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(source)]
        encoded = subprocess.run(arguments, capture_output=True)
        self.assertEqual(encoded.returncode, 0, encoded.stderr.decode())
        media = clip.probe(source)
        self.assertAlmostEqual(media["video_duration_seconds"], 3, delta=1 / 30)
        self.assertAlmostEqual(media["container_duration_seconds"], 6, delta=1 / 30)
        plan.write_text(json.dumps({"clips": [self.selection(4, 5)]}), encoding="utf-8")
        failure = self.cli("create", "--source", source, "--plan", plan, "--project", project, success=False)
        self.assertIn("actual video duration", failure["error"])
        self.assertFalse(project.exists())

    def test_negative_and_zero_length_selections_are_rejected(self):
        for start, end in [(-0.1, 1), (0, 0), (2, 1)]:
            with self.subTest(start=start, end=end):
                self.assert_plan_rejected([self.selection(start, end)], "negative")

    def test_nonfinite_and_boolean_fields_are_rejected(self):
        for field in ("source_start", "source_end", "speed"):
            for value in (True, False, math.nan, math.inf, -math.inf):
                with self.subTest(field=field, value=value):
                    supplied = self.selection()
                    supplied[field] = value
                    self.assert_plan_rejected([supplied], "finite")

    def test_invalid_plan_leaves_no_project_or_parent_output(self):
        directory, plan, ignored = self.paths("invalid-input")
        plan.write_text('{"clips":[{"source_start":0,"source_end":NaN,"decision":"选择"}]}', encoding="utf-8")
        project = directory / "must-not-exist" / "project.json"
        self.cli("create", "--source", self.source, "--plan", plan, "--project", project, success=False)
        self.assertFalse(project.parent.exists())

    def test_protected_speech_cut_on_either_side_is_rejected(self):
        for start, end in [(0.3, 1), (0, 0.5)]:
            with self.subTest(start=start, end=end):
                supplied = self.selection(start, end, protected_speech=[{"start": 0.2, "end": 0.7, "note": "完整发音"}])
                self.assert_plan_rejected([supplied], "protected speech")

    def test_protected_speech_cannot_cross_adjacent_clip_boundary(self):
        supplied = self.selection(0, 1, protected_speech=[{"start": 0.5, "end": 1.4}])
        self.assert_plan_rejected([supplied, self.selection(1, 2)], "crosses a clip boundary")

    def test_partial_caption_never_silently_reuses_whole_text(self):
        with self.assertRaisesRegex(clip.EditError, "explicit replacement"):
            clip.compile_plan([self.selection(0.3, 0.5)], self.cues, self.media)

    def test_split_caption_requires_replacement_for_each_retained_fragment(self):
        selection = self.selection(0.3, 0.4, caption_edits=[{"cue": 1, "source_start": 0.3, "source_end": 0.4, "text": "第一"}])
        with self.assertRaisesRegex(clip.EditError, "explicit replacement"):
            clip.compile_plan([selection, self.selection(0.5, 0.6)], self.cues, self.media)

    def test_explicit_partial_caption_creates_only_replacement_text(self):
        selected = self.selection(0.3, 0.5, caption_edits=[{"cue": 1, "source_start": 0.32, "source_end": 0.48, "text": "中文节选"}])
        _, mapping = clip.compile_plan([selected], self.cues, self.media)
        self.assertEqual(mapping["captions"][0]["text"], "中文节选")
        self.assertAlmostEqual(mapping["captions"][0]["timeline_start"], 0.02)
        self.assertAlmostEqual(mapping["captions"][0]["timeline_end"], 0.18)
        self.assertNotIn("第一句", clip.srt_text(mapping["captions"]))

    def test_submillisecond_cue_cannot_generate_zero_length_srt(self):
        supplied = self.selection(0, 1, caption_edits=[{"cue": 1, "source_start": 0.2, "source_end": 0.2001, "text": "字"}])
        with self.assertRaisesRegex(clip.EditError, "millisecond rounding"):
            clip.compile_plan([supplied], self.cues, self.media)

    def test_speed_changes_captions_and_video_audio_timeline_consistently(self):
        selected = [self.selection(0, 1, 0.5), self.selection(1, 2, 1),
                    self.selection(2, 3, 1.2), self.selection(4, 6, 2)]
        _, mapping = clip.compile_plan(selected, self.cues, self.media)
        self.assertAlmostEqual(mapping["duration_seconds"], 2 + 1 + 1 / 1.2 + 1)
        self.assertAlmostEqual(mapping["captions"][0]["timeline_start"], 0.4)
        self.assertAlmostEqual(mapping["captions"][0]["timeline_end"], 1.2)
        self.assertAlmostEqual(mapping["captions"][-1]["timeline_end"], 2 + 1 + 1 / 1.2 + 0.9)
        directory, project, _ = self.make_project("four-speeds", selected, srt=self.srt)
        rendered = self.cli("render", "--project", project, "--output-dir", directory / "渲染 输出")
        report = rendered["report"]
        self.assertEqual(report["status"], "completed")
        self.assertTrue(report["output_verification"]["checks"]["full_decode"])
        self.assertTrue(report["output_verification"]["checks"]["audio_duration_within_tolerance"])
        self.assertTrue(report["output_verification"]["checks"]["video_duration_within_tolerance"])
        self.assertEqual(report["verification_limits"]["human_listening"], "unverified")
        output_srt = directory / "渲染 输出" / "captions.srt"
        actual_cues = clip.parse_srt(output_srt, mapping["duration_seconds"])
        self.assertEqual(actual_cues[0]["text"], "第一句 中文。")
        self.assertAlmostEqual(actual_cues[0]["source_start"], 0.4)
        audited = self.cli("audit", "--output-dir", directory / "渲染 输出")
        self.assertEqual(audited["status"], "passed")

    def test_edited_project_can_be_rerendered_with_fresh_mapping(self):
        directory, project, _ = self.make_project("edit-project", [self.selection(0, 1)])
        value = json.loads(project.read_text(encoding="utf-8"))
        value["clips"][0]["speed"] = 2
        project.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        inspected = self.cli("inspect", "--project", project)
        self.assertFalse(inspected["creation_mapping_matches_current_clips"])
        self.assertAlmostEqual(inspected["mapping"]["duration_seconds"], 0.5)
        rendered = self.cli("render", "--project", project, "--output-dir", directory / "edited")
        self.assertAlmostEqual(rendered["report"]["output_verification"]["expected_duration_seconds"], 0.5)

    def test_fractional_frame_boundaries_do_not_accumulate_per_clip_drift(self):
        selections = [self.selection(i * 0.28, i * 0.28 + 0.217, 1.2) for i in range(20)]
        directory, project, _ = self.make_project("fractional-boundaries", selections)
        result = self.cli("render", "--project", project, "--output-dir", directory / "render")
        verification = result["report"]["output_verification"]
        expected = 20 * 0.217 / 1.2
        self.assertAlmostEqual(verification["expected_duration_seconds"], expected)
        self.assertLess(abs(verification["actual_media"]["video_duration_seconds"] - expected), 2 / 30)
        self.assertLess(abs(verification["actual_media"]["audio_duration_seconds"] - expected), 0.03)

    def test_boolean_original_caption_number_cannot_masquerade_as_integer(self):
        directory, project, _ = self.make_project("boolean-cue", [self.selection()], srt=self.srt)
        value = json.loads(project.read_text(encoding="utf-8"))
        value["caption_source"]["cues"][0]["cue"] = True
        project.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        output = directory / "must-not-exist"
        failure = self.cli("render", "--project", project, "--output-dir", output, success=False)
        self.assertIn("boolean", failure["error"])
        self.assertFalse(output.exists())

    def test_selected_colors_and_audio_frequencies_survive_cuts_order_and_speed(self):
        directory, _, _ = self.paths("distinct-av-events")
        source = directory / "不同画面 不同声音.mp4"
        arguments = [clip.FFMPEG, "-hide_banner", "-v", "error", "-n"]
        colors = [("red", 400), ("yellow", 600), ("green", 800), ("blue", 1000)]
        for color, frequency in colors:
            arguments += ["-f", "lavfi", "-i", f"color=c={color}:size=160x120:rate=30:duration=1.5",
                          "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration=1.5"]
        pairs = "".join(f"[{i * 2}:v][{i * 2 + 1}:a]" for i in range(4))
        arguments += ["-filter_complex", pairs + "concat=n=4:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
                      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)]
        encoded = subprocess.run(arguments, capture_output=True)
        self.assertEqual(encoded.returncode, 0, encoded.stderr.decode())
        selections = [self.selection(0, 1.5, 0.5), self.selection(3, 4.5, 1.2), self.selection(4.5, 6, 2)]
        render_dir, project, _ = self.make_project("distinct-av-project", selections, source=source)
        output = render_dir / "删中段 混速输出"
        result = self.cli("render", "--project", project, "--output-dir", output)
        self.assertAlmostEqual(result["report"]["mapping"]["duration_seconds"], 5)
        self.assertTrue(result["report"]["output_verification"]["passed"])
        video = output / "edited.mp4"
        # Interior windows avoid ordinary H.264/AAC boundary and frame rounding.
        expected = [(1.5, (255, 0, 0), 400), (3.625, (0, 128, 0), 800), (4.625, (0, 0, 255), 1000)]
        observations = []
        for midpoint, color, frequency in expected:
            with self.subTest(midpoint=midpoint, frequency=frequency):
                frame = subprocess.run([clip.FFMPEG, "-v", "error", "-ss", str(midpoint), "-i", str(video),
                                        "-map", "0:v:0", "-frames:v", "1", "-vf", "crop=2:2:80:60,format=rgb24",
                                        "-f", "rawvideo", "pipe:1"], capture_output=True)
                self.assertEqual(frame.returncode, 0, frame.stderr.decode())
                self.assertEqual(len(frame.stdout), 12)
                pixel = tuple(frame.stdout[:3])
                for actual, wanted in zip(pixel, color):
                    self.assertLessEqual(abs(actual - wanted), 25)
                audio = subprocess.run([clip.FFMPEG, "-v", "error", "-ss", str(midpoint - 0.2), "-i", str(video),
                                        "-t", "0.4", "-map", "0:a:0", "-ac", "1", "-ar", "8000",
                                        "-f", "s16le", "pipe:1"], capture_output=True)
                self.assertEqual(audio.returncode, 0, audio.stderr.decode())
                samples = struct.unpack("<" + "h" * (len(audio.stdout) // 2), audio.stdout)
                self.assertGreater(len(samples), 3000)
                self.assertGreater(max(samples), 1000)
                crossings = sum(left <= 0 < right for left, right in zip(samples, samples[1:]))
                measured_frequency = crossings * 8000 / (len(samples) - 1)
                self.assertLessEqual(abs(measured_frequency - frequency), 12)
                observations.append({"output_second": midpoint, "expected_rgb": color, "actual_rgb": pixel,
                                     "expected_frequency_hz": frequency, "measured_frequency_hz": measured_frequency,
                                     "rgb_channel_tolerance": 25, "frequency_tolerance_hz": 12})
        (output / "av-event-observations.json").write_text(json.dumps(observations, indent=2), encoding="utf-8")

    def test_changed_source_fails_before_render_directory_creation(self):
        directory, _, _ = self.paths("stale-source")
        source = directory / "source.mp4"
        source.write_bytes(self.source.read_bytes())
        directory2, project, _ = self.make_project("stale-project", [self.selection()], source=source)
        with source.open("ab") as handle:
            handle.write(b"changed")
        output = directory2 / "must-not-exist"
        failed = self.cli("render", "--project", project, "--output-dir", output, success=False)
        self.assertIn("SHA-256", failed["error"])
        self.assertFalse(output.exists())

    def test_changed_caption_source_fails_before_render_directory_creation(self):
        directory, _, _ = self.paths("stale-caption")
        srt = directory / "source.srt"
        srt.write_bytes(self.srt.read_bytes())
        directory2, project, _ = self.make_project("stale-caption-project", [self.selection()], srt=srt)
        srt.write_text(srt.read_text(encoding="utf-8").replace("第一句", "改动句"), encoding="utf-8")
        output = directory2 / "must-not-exist"
        failed = self.cli("render", "--project", project, "--output-dir", output, success=False)
        self.assertIn("SHA-256", failed["error"])
        self.assertFalse(output.exists())

    def test_source_alias_and_existing_project_are_never_overwritten(self):
        directory, plan, project = self.paths("alias")
        plan.write_text(json.dumps({"clips": [self.selection()]}), encoding="utf-8")
        before = clip.digest(self.source)
        alias = directory / "source-alias.json"
        alias.symlink_to(self.source)
        self.cli("create", "--source", self.source, "--plan", plan, "--project", alias, success=False)
        self.assertEqual(before, clip.digest(self.source))
        project.write_text("keep this file", encoding="utf-8")
        self.cli("create", "--source", self.source, "--plan", plan, "--project", project, success=False)
        self.assertEqual(project.read_text(encoding="utf-8"), "keep this file")

    def test_output_alias_or_existing_directory_preserves_inputs(self):
        directory, project, _ = self.make_project("output-alias", [self.selection()])
        before = clip.digest(self.source)
        self.cli("render", "--project", project, "--output-dir", self.source, success=False)
        self.cli("render", "--project", project, "--output-dir", directory, success=False)
        self.assertEqual(before, clip.digest(self.source))
        self.assertFalse((directory / "edited.mp4").exists())

    def test_failed_encode_preserves_failed_report_without_completed_status(self):
        directory, project, _ = self.make_project("failed-render", [self.selection()])
        output = directory / "failed-output"
        self.cli("render", "--project", project, "--output-dir", output,
                 "--ffmpeg", directory / "missing-executable", success=False)
        report = json.loads((output / "validation-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "failed")
        self.assertIn("error", report)
        self.cli("audit", "--output-dir", output, success=False)

    def test_corrupted_output_is_rejected_by_fresh_audit(self):
        directory, project, _ = self.make_project("audit-corruption", [self.selection()])
        output = directory / "render"
        self.cli("render", "--project", project, "--output-dir", output)
        video = output / "edited.mp4"
        with video.open("ab") as handle:
            handle.write(b"corruption")
        failed = self.cli("audit", "--output-dir", output, success=False)
        self.assertIn("changed", failed["error"])

    def test_srt_overlap_out_of_source_and_boolean_edit_bounds_rejected(self):
        directory, _, _ = self.paths("invalid-srt")
        for content in ("1\n00:00:00,000 --> 00:00:01,000\n一\n\n2\n00:00:00,500 --> 00:00:01,500\n二\n",
                        "1\n00:00:05,000 --> 00:00:07,000\n过长\n"):
            file = directory / (uuid.uuid4().hex + ".srt")
            file.write_text(content, encoding="utf-8")
            with self.assertRaises(clip.EditError):
                clip.parse_srt(file, 6)
        supplied = self.selection(0, 1, caption_edits=[{"cue": 1, "source_start": True, "source_end": 0.6, "text": "一"}])
        with self.assertRaisesRegex(clip.EditError, "boolean"):
            clip.compile_plan([supplied], self.cues, self.media)


if __name__ == "__main__":
    unittest.main()
