#!/usr/bin/env python3
"""Audit audible event manifests for layered or sequential source reuse."""
import argparse
import json
import math
from pathlib import Path


def audit(events):
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
    findings=[]
    for n,(i,a) in enumerate(active):
        for j,b in active[n+1:]:
            overlap=min(a["timeline_end"],b["timeline_end"])-max(a["timeline_start"],b["timeline_start"])
            reused=min(a["source_end"],b["source_end"])-max(a["source_start"],b["source_start"])
            if overlap > 0.001:
                findings.append({"kind":"audible_layer_overlap","events":[i+1,j+1],"seconds":overlap,"same_material":a["material"]==b["material"]})
            if a["material"]==b["material"] and reused > 0.001:
                findings.append({"kind":"reused_source_interval","events":[i+1,j+1],"seconds":reused})
    return {"status":"review_required" if findings else "passed_manifest_checks","event_count":len(events),"audible_event_count":len(active),"findings":findings,"limits":{"complete_track_inventory":"caller_must_verify","waveform_duplication":"not_checked","human_listening":"unverified"}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",required=True)
    p.add_argument("--report",required=True)
    args=p.parse_args()
    source=Path(args.manifest).resolve(); output=Path(args.report).resolve()
    if source==output or output.exists():
        raise ValueError("Use a new report path")
    result=audit(json.loads(source.read_text(encoding="utf-8")))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))
    return 1 if result["findings"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
