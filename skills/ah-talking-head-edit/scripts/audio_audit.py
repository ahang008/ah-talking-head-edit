#!/usr/bin/env python3
"""Audit audible event manifests for layered or sequential source reuse."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def audit(events, inventory=None):
    if not isinstance(events, list) or not events:
        raise ValueError("Provide a nonempty list of all audible events")
    active = []
    for i, e in enumerate(events):
        if not isinstance(e, dict) or not isinstance(e.get("material"), str) or not e["material"].strip():
            raise ValueError("Each event needs a verified material identity")
        if type(e.get("audible")) is not bool:
            raise ValueError("Each event needs an explicit audible boolean")
        for k in ("source_start", "source_end", "timeline_start", "timeline_end"):
            v=e.get(k)
            if type(v) not in (int,float) or not math.isfinite(v) or v < 0:
                raise ValueError("Invalid event time")
        if e["source_end"] <= e["source_start"] or e["timeline_end"] <= e["timeline_start"]:
            raise ValueError("Invalid event interval")
        if e["audible"]:
            active.append((i,e))
    scope_problems=[]
    if inventory is not None:
        expected=inventory.get("audible_track_ids") if isinstance(inventory,dict) else None
        duration=inventory.get("duration_seconds") if isinstance(inventory,dict) else None
        if not isinstance(expected,list) or not expected or any(not isinstance(x,str) or not x.strip() for x in expected) or len(set(expected))!=len(expected):
            raise ValueError("Inventory requires unique audible track IDs")
        if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:
            raise ValueError("Inventory requires a finite positive duration")
        actual=set()
        for i,e in active:
            track=e.get("track_id")
            if not isinstance(track,str) or not track.strip():
                scope_problems.append({"kind":"missing_track_identity","event":i+1})
            else:actual.add(track)
            if e["timeline_end"]>duration+0.001:
                scope_problems.append({"kind":"timeline_out_of_bounds","event":i+1})
        if actual!=set(expected):
            scope_problems.append({"kind":"track_set_mismatch","missing":sorted(set(expected)-actual),"unexpected":sorted(actual-set(expected))})
    findings=[]
    if inventory is not None:
        cursor=0.0
        for _,e in sorted(active,key=lambda pair:pair[1]["timeline_start"]):
            start=min(duration,e["timeline_start"])
            if start-cursor>=0.25:
                findings.append({"kind":"uncovered_timeline_interval","start":cursor,"end":start,"seconds":start-cursor})
            cursor=max(cursor,min(duration,e["timeline_end"]))
        if duration-cursor>=0.25:
            findings.append({"kind":"uncovered_timeline_interval","start":cursor,"end":duration,"seconds":duration-cursor})
    for n,(i,a) in enumerate(active):
        for j,b in active[n+1:]:
            overlap=min(a["timeline_end"],b["timeline_end"])-max(a["timeline_start"],b["timeline_start"])
            reused=min(a["source_end"],b["source_end"])-max(a["source_start"],b["source_start"])
            if overlap > 0.001:
                findings.append({"kind":"audible_layer_overlap","events":[i+1,j+1],"seconds":overlap,"same_material":a["material"]==b["material"]})
            if a["material"]==b["material"] and reused > 0.001:
                findings.append({"kind":"reused_source_interval","events":[i+1,j+1],"seconds":reused})
    status="incomplete_scope" if scope_problems else "review_required" if findings else "passed_declared_inventory_checks" if inventory is not None else "passed_scoped_checks"
    return {"status":status,"scope":"declared_inventory" if inventory is not None else "supplied_events_only","scope_problems":scope_problems,"whole_video_acceptance":"not_established","event_count":len(events),"audible_event_count":len(active),"findings":findings,"limits":{"complete_track_inventory":"caller_must_verify","within_track_event_completeness":"not_independently_verified","event_coverage_is_not_acoustic_silence":True,"waveform_duplication":"not_checked","human_listening":"unverified"}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",required=True)
    p.add_argument("--report",required=True)
    p.add_argument("--inventory",help="JSON with audible_track_ids, duration_seconds, snapshot_sha256")
    p.add_argument("--snapshot",help="Current project snapshot bound by the inventory")
    args=p.parse_args()
    source=Path(args.manifest).resolve(); output=Path(args.report).resolve()
    additional=[Path(x).resolve() for x in (args.inventory,args.snapshot) if x]
    if source==output or output in additional or output.exists():
        raise ValueError("Use a new report path")
    if bool(args.inventory)!=bool(args.snapshot):
        raise ValueError("Provide inventory and snapshot together")
    inventory=None
    if args.inventory:
        inventory_raw=Path(args.inventory).read_bytes()
        inventory=json.loads(inventory_raw.decode("utf-8"))
        snapshot_hash=hashlib.sha256(Path(args.snapshot).read_bytes()).hexdigest()
        if not isinstance(inventory,dict) or inventory.get("snapshot_sha256")!=snapshot_hash:
            raise ValueError("Inventory differs from current snapshot hash")
    raw=source.read_bytes()
    result=audit(json.loads(raw.decode("utf-8")),inventory)
    result["manifest_sha256"]=hashlib.sha256(raw).hexdigest()
    if inventory is not None:
        result["inventory_sha256"]=hashlib.sha256(inventory_raw).hexdigest()
        result["snapshot_sha256"]=snapshot_hash
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))
    return 1 if result["findings"] or result["scope_problems"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
