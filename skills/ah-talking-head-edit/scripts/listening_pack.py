#!/usr/bin/env python3
"""Export version-bound listening windows, not listening verdicts."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import wave

from clip import FFMPEG, load_project, probe
from pause_audit import digest, check_render_hashes


def window(center, context, duration):
    if not all(math.isfinite(x) for x in (center,context,duration)) or not 0<=center<=duration or context<=0 or duration<=0:
        raise ValueError("Invalid listening window")
    return [max(0,center-context),min(duration,center+context)]


def shortlist(rows, limit):
    if type(limit) is not int or limit<1:raise ValueError("Limit must be positive")
    ranked=sorted(enumerate(rows,1),key=lambda x:(not bool(x[1]['crossed_cuts']),not bool(x[1]['explicit_reason_required']),-x[1]['seconds'],x[0]))
    return ranked[:limit], [n for n,_ in ranked[limit:]]


def extract(source, stream, interval, output, origin=0):
    a,b=interval
    r=subprocess.run([FFMPEG,"-hide_banner","-nostdin","-v","error","-n","-i",str(source),
                      "-map",f"0:{stream}","-vn","-af",
                      f"asetpts=PTS-({origin:.12g})/TB,aresample=48000:async=1:first_pts=0,atrim=start={a:.12g}:end={b:.12g},asetpts=PTS-STARTPTS",
                      "-t",str(b-a),"-c:a","pcm_s16le",str(output)],capture_output=True,text=True)
    if r.returncode:raise RuntimeError(r.stderr[-2000:])
    with wave.open(str(output),"rb") as f:
        length=f.getnframes()/f.getframerate()
    if abs(length-(b-a))>0.05:raise ValueError("Listening window audio is truncated")
    return {"file":output.name,"sha256":digest(output),"seconds":length,"range":interval}


def verify_pack(directory, hashes):
    index=json.loads((directory/'listening-index.json').read_text(encoding='utf-8'))
    for key,value in hashes.items():
        if index.get(key)!=value:raise ValueError("Listening pack belongs to another version")
    for item in index['items']:
        for sample in [item['edited']]+item['source_contexts']:
            path=(directory/sample['file']).resolve()
            if path.parent!=directory.resolve() or digest(path)!=sample['sha256']:
                raise ValueError("Listening file changed or escaped pack directory")
    return {'status':'verified_unlistened','items':len(index['items']),'human_listening':'unverified'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("video","project","render-report","pause-report"):
        p.add_argument("--"+name,required=True)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output-dir')
    mode.add_argument('--verify-dir')
    p.add_argument("--context",type=float,default=2)
    p.add_argument("--limit",type=int,default=10)
    p.add_argument("--cut",type=int,action="append",default=[],help="Also export a join after this 1-based clip")
    args=p.parse_args()
    video,project,render,pause=(Path(x).resolve() for x in (args.video,args.project,args.render_report,args.pause_report))
    if not math.isfinite(args.context) or args.context<=0:raise ValueError("Invalid context")
    _,data,source,media,clips,mapping,project_hash=load_project(project)
    hashes=[digest(x) for x in (video,render,pause)]
    check_render_hashes(json.loads(render.read_text()),project_hash,hashes[0])
    report=json.loads(pause.read_text())
    if report.get('status')!='candidates_only' or report.get('video_sha256')!=hashes[0] or report.get('project_sha256')!=project_hash or report.get('render_report_sha256')!=hashes[1]:
        raise ValueError("Pause report belongs to another version")
    current={'video_sha256':hashes[0],'project_sha256':project_hash,'render_report_sha256':hashes[1],'pause_report_sha256':hashes[2]}
    if args.verify_dir:
        print(json.dumps(verify_pack(Path(args.verify_dir).resolve(),current)));return
    out=Path(args.output_dir).resolve()
    if out.exists() or any(out==x or out in x.parents for x in (video,project,render,pause,source)):
        raise ValueError("Use a fresh output directory that cannot contain an input")
    video_media=probe(video)
    duration=video_media['audio_duration_seconds']
    selected,remaining=shortlist(report['candidates'],args.limit)
    items=[]
    for n,row in selected:
        # Include the whole candidate, plus context on both sides.
        a=max(0,row['start']-args.context);b=min(duration,row['end']+args.context)
        items.append({'id':f'candidate-{n:03d}','candidate':n,'range':[a,b],
                      'joins':[i for i,c in enumerate(mapping['clips'][:-1],1) if a<=c['timeline_end']<=b]})
    for n in args.cut:
        if not 1<=n<len(clips):raise ValueError("Cut number is outside project")
        items.append({'id':f'cut-{n:03d}','range':window(mapping['clips'][n-1]['timeline_end'],args.context,duration),'joins':[n]})
    if len({x['id'] for x in items})!=len(items):raise ValueError("Duplicate cut request")
    out.mkdir(parents=True)
    completed=[]
    for item in items:
        name=item['id']
        item['edited']=extract(video,video_media['audio_stream_index'],item['range'],out/f'{name}-edited.wav')
        item['edited_join_markers']=[{'clip':n,'at_window_seconds':mapping['clips'][n-1]['timeline_end']-item['range'][0]} for n in item['joins']]
        item['source_contexts']=[]
        for n in item['joins']:
            for side,index,key in (('left',n-1,'source_end'),('right',n,'source_start')):
                c=clips[index]
                sample=extract(source,media['audio_stream_index'],window(c[key],args.context,media['audio_duration_seconds']),out/f'{name}-join-{n:03d}-{side}-source.wav',media['video_origin_seconds'])
                sample.update({'clip':index+1,'side':side,'source_boundary':c[key],'boundary_at_window_seconds':c[key]-sample['range'][0],'edited_speed':c['speed'],'sample_speed':1})
                item['source_contexts'].append(sample)
        if not item['joins']:
            center=sum(item['range'])/2
            for i,c in enumerate(mapping['clips']):
                if c['timeline_start']<=center<=c['timeline_end']:
                    original=c['source_start']+(center-c['timeline_start'])*c['speed']
                    sample=extract(source,media['audio_stream_index'],window(original,args.context,media['audio_duration_seconds']),out/f'{name}-source.wav',media['video_origin_seconds'])
                    sample.update({'clip':i+1,'source_center':original,'edited_speed':c['speed'],'sample_speed':1})
                    item['source_contexts'].append(sample);break
        item['human_listening']='unverified';completed.append(item)
    if hashes!=[digest(x) for x in (video,render,pause)] or project_hash!=digest(project) or digest(source)!=data['source']['sha256']:
        raise ValueError("Inputs changed during listening export")
    result={'status':'exported_unlistened',**current,'context_seconds':args.context,'items':completed,
            'remaining_candidate_ids':remaining,'limits':['Source windows are separate original-speed contexts, not an invented before-edit sequence.','Edited windows preserve actual master speed and loudness; source-to-master mapping has render sample/frame quantization.','Shortlist is not full-video acceptance; exported WAV files do not prove listening.']}
    (out/'listening-index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'items':len(completed),'remaining_candidates':len(remaining)}))

if __name__=='__main__':main()
