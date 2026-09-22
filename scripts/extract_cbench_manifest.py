#!/usr/bin/env python3
"""Extract small location/build manifests from retained, sampled cBench evidence."""
import json
from pathlib import Path


def extract(root: Path):
    retained = root / 'preserved/cbench'
    inventory = json.loads((retained / 'configs/cbench_hotspots_dataset1_28.json').read_text())
    builds = {p['program']: p for p in json.loads(
        (retained / 'configs/cbench_build_run_dataset1.json').read_text())}
    mad = json.loads((retained / 'consumer_mad/program.json').read_text())
    builds[mad['program']] = mad
    hotspots, programs = [], []
    for entry in inventory['programs']:
        name = entry['program']
        hotspot = entry.get('primary_hotspot')
        row = {'program': name, 'status': entry['status']}
        if hotspot:
            source = Path(hotspot['source'])
            row.update(file=source.name, path=str(source.relative_to(root)),
                       function=hotspot['function'], start_line=hotspot['start_line'],
                       end_line=hotspot['end_line'])
        else:
            row['reason'] = 'Build blocked; full diagnostics remain in the evidence inventory'
        hotspots.append(row)
        if not hotspot:
            continue
        original = builds[name]
        program = {key: original[key] for key in (
            'program', 'command', 'dataset_id', 'native_repeat', 'inputs', 'outputs',
            'environment', 'link_flags')}
        program['inputs'] = list(original['inputs'])
        program['source_dir'] = str(Path(original['source_dir']).relative_to(root))
        program['tus'] = [{k: u[k] for k in ('id', 'source', 'flags')} for u in original['tus']]
        programs.append(program)
    return ({'schema': 'cbench.locations.v1', 'evidence':
             'preserved/cbench/configs/cbench_hotspots_dataset1_28.json', 'programs': hotspots},
            {'schema': 'cbench.builds.v1', 'programs': programs})


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    locations, builds = extract(root)
    for name, data in [('cbench_hotspots.json', locations), ('cbench_builds.json', builds)]:
        (root / 'configs' / name).write_text(json.dumps(data, indent=2) + '\n')
    print(f"Extracted {sum(p['status'] == 'ready' for p in locations['programs'])} ready hotspots")
