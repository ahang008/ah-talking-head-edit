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


def audit(pause, review, video_hash, project_hash, pause_hash, native=False, packs=None):
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
        if 'listening_pack' in row:
            ref=row['listening_pack']
            if not isinstance(ref,dict) or set(ref)!={'index_sha256','item_id'} or not all(isinstance(x,str) and x.strip() for x in ref.values()):
                problems.append({'kind':'invalid_listening_reference','candidate':n})
                continue
            pack=(packs or {}).get(ref['index_sha256'])
            if pack is None:
                problems.append({'kind':'unverified_listening_pack','candidate':n})
                continue
            if any(pack.get(k)!=v for k,v in [('video_sha256',video_hash),('project_sha256',project_hash),('pause_report_sha256',pause_hash)]):
                problems.append({'kind':'stale_listening_pack','candidate':n})
                continue
            matches=[item for item in pack['items'] if item.get('id')==ref['item_id']]
            if len(matches)!=1 or matches[0].get('candidate')!=n:
                problems.append({'kind':'wrong_listening_item','candidate':n})
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
    p.add_argument("--listening-dir",action="append",default=[],help="Verify a referenced listening pack; repeat for multiple packs")
    args=p.parse_args()
    inputs=[Path(x).resolve() for x in (args.video,args.project,args.pause_report,args.review)]
    output=Path(args.report).resolve()
    if output.exists() or output in inputs:raise ValueError("Use a fresh report path")
    hashes=[digest(x) for x in inputs]
    packs={}; pack_paths={}
    if args.listening_dir:
        from listening_pack import verify_pack
        for name in args.listening_dir:
            directory=Path(name).resolve();index_path=directory/'listening-index.json'
            index_hash=digest(index_path)
            verify_pack(directory,{'video_sha256':hashes[0],'project_sha256':hashes[1],'pause_report_sha256':hashes[2]})
            pack=json.loads(index_path.read_text(encoding='utf-8'))
            if digest(index_path)!=index_hash:raise ValueError('Listening index changed during verification')
            packs[index_hash]=pack;pack_paths[index_hash]=directory
    result=audit(json.loads(inputs[2].read_text(encoding="utf-8")),
                 json.loads(inputs[3].read_text(encoding="utf-8")),*hashes[:3],native=args.native,packs=packs)
    if hashes!=[digest(x) for x in inputs]:raise ValueError("An input changed during review audit")
    for h,directory in pack_paths.items():
        if digest(directory/'listening-index.json')!=h:raise ValueError('Listening index changed during review audit')
        verify_pack(directory,{'video_sha256':hashes[0],'project_sha256':hashes[1],'pause_report_sha256':hashes[2]})
    result['verified_listening_index_sha256']=list(packs)
    result["input_sha256"]={name:h for name,h in zip(("video","project","pause_report","review"),hashes)}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({"status":result["status"],"problem_count":len(result["problems"])},ensure_ascii=False))
    return 1 if result["problems"] else 0

if __name__=="__main__":raise SystemExit(main())
