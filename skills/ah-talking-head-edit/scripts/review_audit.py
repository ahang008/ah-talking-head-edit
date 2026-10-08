#!/usr/bin/env python3
"""Check current-version review records; does not perform or certify listening."""
import argparse
import hashlib
import json
from pathlib import Path

STAGES = ("audio_inventory", "semantics", "cut_listening", "subtitle_wording",
          "subtitle_sync", "full_listening")
NATIVE_STAGES = ("native_captions", "caption_coverage", "native_persistence")


def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()


def audit(pause, review, video_hash, project_hash, pause_hash, native=False):
    problems=[]
    for name,current in (("video_sha256",video_hash),("project_sha256",project_hash)):
        if pause.get(name)!=current or review.get(name)!=current:
            problems.append({"kind":"stale_version","field":name})
    if review.get("pause_report_sha256")!=pause_hash:
        problems.append({"kind":"stale_pause_report"})
    rows=pause.get("candidates")
    if pause.get("status")!="candidates_only" or not isinstance(rows,list):
        raise ValueError("Expected a pause candidate report")
    decisions=review.get("decisions",[])
    if not isinstance(decisions,list):raise ValueError("decisions must be an array")
    indexed={}
    for row in decisions:
        if not isinstance(row,dict):raise ValueError("Invalid decision")
        n=row.get("candidate")
        if type(n) is not int or not 1<=n<=len(rows) or n in indexed:
            raise ValueError("Invalid or duplicate candidate number")
        indexed[n]=row
    for n in range(1,len(rows)+1):
        row=indexed.get(n,{})
        # DELETE describes an intended edit, not a resolved finding on this master.
        # A new edit needs a new render, audit and review record.
        if row.get("decision")!="KEEP":
            problems.append({"kind":"unresolved_candidate","candidate":n})
        elif not all(isinstance(row.get(k),str) and row[k].strip() for k in ("reason","reviewer","listening_evidence")):
            problems.append({"kind":"missing_candidate_evidence","candidate":n})
    stages=review.get("stages",{})
    if not isinstance(stages,dict):raise ValueError("stages must be an object")
    for name in STAGES+(NATIVE_STAGES if native else ()):
        item=stages.get(name,{})
        if not isinstance(item,dict):raise ValueError("Invalid stage record")
        if item.get("status")!="verified" or not all(isinstance(item.get(k),str) and item[k].strip() for k in ("reviewer","evidence")):
            problems.append({"kind":"missing_stage_evidence","stage":name})
    return {"status":"needs_review" if problems else "review_records_complete",
            "candidate_count":len(rows),"problems":problems,
            "limits":{"human_evidence":"reviewer_declarations_not_independently_verified",
                      "listening_performed_by_script":False,
                      "media_and_native_acceptance":"requires_separate_actual_checks"}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("video","project","pause-report","review","report"):
        p.add_argument("--"+name,required=True)
    p.add_argument("--native",action="store_true")
    args=p.parse_args()
    inputs=[Path(x).resolve() for x in (args.video,args.project,args.pause_report,args.review)]
    output=Path(args.report).resolve()
    if output.exists() or output in inputs:raise ValueError("Use a fresh report path")
    hashes=[digest(x) for x in inputs]
    result=audit(json.loads(inputs[2].read_text(encoding="utf-8")),
                 json.loads(inputs[3].read_text(encoding="utf-8")),*hashes[:3],native=args.native)
    if hashes!=[digest(x) for x in inputs]:raise ValueError("An input changed during review audit")
    result["input_sha256"]={name:h for name,h in zip(("video","project","pause_report","review"),hashes)}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({"status":result["status"],"problem_count":len(result["problems"])},ensure_ascii=False))
    return 1 if result["problems"] else 0

if __name__=="__main__":raise SystemExit(main())
