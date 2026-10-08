#!/usr/bin/env python3
"""Find low-energy review candidates in a rendered master, without editing it."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from clip import FFMPEG, probe, load_project


def candidates(log, duration, cuts, minimum=0.25):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid duration")
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError("Invalid candidate threshold")
    if any(not math.isfinite(x) or not 0 < x < duration for x in cuts):
        raise ValueError("Cut positions must lie inside the master")
    rows, start = [], None
    for kind, value in re.findall(r"silence_(start|end):\s*([-+0-9.eE]+)", log):
        time = float(value)
        if not math.isfinite(time):
            raise ValueError("Invalid silence event")
        if kind == "start":
            if start is not None:
                raise ValueError("Unpaired silence events")
            start = max(0.0, time)
        else:
            if start is None:
                raise ValueError("Silence end without start")
            end = min(duration, time)
            if end < start:
                raise ValueError("Reversed silence events")
            rows.append((start, end)); start = None
    if start is not None:
        rows.append((start, duration))
    result = []
    for a, b in rows:
        if b - a + 1e-9 >= minimum:
            result.append({"start": a, "end": b, "seconds": b-a,
                           "crossed_cuts": [x for x in cuts if a < x < b],
                           "priority_review": b-a >= 0.4,
                           "explicit_reason_required": b-a >= 0.8,
                           "decision": "CHECK"})
    return result


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def check_render_hashes(render, project_hash, video_hash):
    if render.get("status") != "completed" or render.get("project_sha256") != project_hash or render.get("artifacts",{}).get("video",{}).get("sha256") != video_hash:
        raise ValueError("Master/project hashes differ from completed render evidence")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", required=True)
    p.add_argument("--project", required=True, help="Independent editable project")
    p.add_argument("--render-report", required=True, help="Report from this master's independent render")
    p.add_argument("--report", required=True)
    p.add_argument("--noise-db", type=float, default=-32)
    p.add_argument("--minimum", type=float, default=0.25)
    args = p.parse_args()
    video, project, output = (Path(x).resolve() for x in (args.video,args.project,args.report))
    if output.exists() or output in (video,project):
        raise ValueError("Use a fresh report path")
    if not math.isfinite(args.noise_db) or args.noise_db >= 0 or not math.isfinite(args.minimum) or args.minimum <= 0:
        raise ValueError("Invalid low-energy thresholds")
    media = probe(video)
    duration = media["audio_duration_seconds"]
    _, _, _, _, _, mapping, project_hash = load_project(project)
    render_path = Path(args.render_report).resolve()
    if output == render_path:
        raise ValueError("Report cannot overwrite render evidence")
    render = json.loads(render_path.read_text(encoding="utf-8"))
    if abs(mapping["duration_seconds"]-duration) > 0.15:
        raise ValueError("Master duration differs from project; verify matching version")
    cuts = [x["timeline_end"] for x in mapping["clips"][:-1]]
    before = digest(video)
    render_hash = digest(render_path)
    check_render_hashes(render,project_hash,before)
    r = subprocess.run([FFMPEG,"-hide_banner","-nostdin","-i",str(video),"-map","0:a:0",
                        "-af",f"silencedetect=noise={args.noise_db}dB:d={args.minimum}",
                        "-vn","-f","null","-"], capture_output=True,text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])
    if before != digest(video):
        raise ValueError("Master changed during audit")
    if project_hash != digest(project) or render_hash != digest(render_path):
        raise ValueError("Project or render evidence changed during audit")
    gaps = candidates(r.stderr,duration,cuts,args.minimum)
    result = {"status":"candidates_only", "video_sha256":before,
              "project_sha256":project_hash, "render_report_sha256":render_hash, "duration":duration,
              "noise_db":args.noise_db, "minimum":args.minimum, "candidates":gaps,
              "summary":{"count":len(gaps), "cross_cut_count":sum(bool(x["crossed_cuts"]) for x in gaps),
                         "longest_seconds":max((x["seconds"] for x in gaps),default=0)},
              "limits":{"project_matches_master":"hashes_match_supplied_render_report",
                        "speech_absence":"not_proven", "human_listening":"unverified"}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result["summary"],ensure_ascii=False))

if __name__ == "__main__":
    main()
