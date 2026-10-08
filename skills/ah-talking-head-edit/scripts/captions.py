#!/usr/bin/env python3
"""Review native-recognized SRT without changing cue segmentation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from clip import EditError, parse_srt, srt_text


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(cues, duration):
    tolerance = 0.00051
    gaps = []
    cursor = 0.0
    for cue in cues:
        if cue['source_start'] > cursor + tolerance:
            gaps.append([cursor, cue['source_start']])
        cursor = cue['source_end']
    if cursor < duration - tolerance:
        gaps.append([cursor, duration])
    return {'status': 'passed' if not gaps else 'failed', 'cue_count': len(cues),
            'duration_seconds': duration, 'gaps': gaps,
            'human_listening': 'unverified', 'wording_audio_alignment': 'unverified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'audit'])
    parser.add_argument('--srt', required=True)
    parser.add_argument('--duration', required=True, type=float)
    parser.add_argument('--output')
    parser.add_argument('--corrections', help='JSON list of {cue, before, after}')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0:
        raise EditError('Duration must be finite and positive')
    source = Path(args.srt).resolve()
    report_path = Path(args.report).resolve()
    output = Path(args.output).resolve() if args.output else None
    correction_path = Path(args.corrections).resolve() if args.corrections else None
    inputs = {source} | ({correction_path} if correction_path else set())
    outputs = [report_path] + ([output] if output else [])
    if len(set(outputs)) != len(outputs) or any(p in inputs or p.exists() for p in outputs):
        raise EditError('Use distinct new output and report paths; do not overwrite inputs')
    cues = parse_srt(source, args.duration + 0.00051)
    input_hash = sha(source)
    changes = []
    if args.command == 'prepare':
        if output is None:
            raise EditError('prepare requires --output')
        corrections = json.loads(correction_path.read_text(encoding='utf-8')) if correction_path else []
        if not isinstance(corrections, list):
            raise EditError('Corrections must be a list')
        seen = set()
        for item in corrections:
            if not isinstance(item, dict) or set(item) != {'cue', 'before', 'after'}:
                raise EditError('Each correction requires exactly cue, before, after')
            n = item['cue']
            if type(n) is not int or n < 1 or n > len(cues) or n in seen:
                raise EditError('Correction cue must be a unique existing integer')
            seen.add(n)
            cue = cues[n - 1]
            if cue['text'] != item['before'] or not isinstance(item['after'], str) or not item['after'].strip():
                raise EditError('Correction original text mismatch or empty replacement')
            changes.append(dict(item))
            cue['text'] = item['after']
        original_ranges = [(c['source_start'], c['source_end']) for c in cues]
        cues[0]['source_start'] = 0.0
        for index, cue in enumerate(cues):
            cue['source_end'] = cues[index + 1]['source_start'] if index + 1 < len(cues) else args.duration
        mapped = [{'timeline_start': c['source_start'], 'timeline_end': c['source_end'], 'text': c['text']} for c in cues]
        text = srt_text(mapped)
        # Validate millisecond rounding before writing any result.
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            check = Path(temp) / 'check.srt'
            check.write_text(text, encoding='utf-8')
            checked = parse_srt(check, args.duration + 0.00051)
        if len(checked) != len(cues):
            raise EditError('Cue count changed')
        result = audit(checked, args.duration)
        if result['status'] != 'passed':
            raise EditError('Prepared SRT does not cover the requested timeline')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as handle:
            handle.write(text)
        result.update({'output': str(output), 'output_sha256': sha(output),
                       'segmentation_preserved': True, 'text_changes': changes,
                       'timing_changes': [{'cue': i + 1, 'before': list(old),
                           'after': [c['source_start'], c['source_end']]}
                           for i, (old, c) in enumerate(zip(original_ranges, cues))
                           if old != (c['source_start'], c['source_end'])]})
    else:
        if output or correction_path:
            raise EditError('audit is read-only and accepts no output or corrections')
        result = audit(cues, args.duration)
    result.update({'input': str(source), 'input_sha256': input_hash,
                   'caption_origin': 'caller_must_verify_native_recognition'})
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'status': result['status'], 'cue_count': len(cues), 'report': str(report_path)}, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (EditError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
