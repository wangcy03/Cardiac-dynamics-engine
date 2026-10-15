"""Generate paired no-assist/causal-demo traces from a shared state, plus an offline viewer.

Run from project root: python -m examples.run_demo
"""
from __future__ import annotations
import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from iabp import __version__
from iabp.engine import Engine
from iabp.model import ModelConfig
from iabp.scenarios import ThresholdDemoController, add_sinus_schedule
from tools.viewer import write_viewer

def record(engine: Engine, end_us: int, assisted: bool) -> dict:
    start = engine.now_us
    controller = ThresholdDemoController() if assisted else None
    rows, samples = ([], [])
    for t in range(start, end_us + 1, 1000):
        available = engine.advance_to(t)
        samples.extend(available)
        if controller:
            for command in controller.on_samples(available, t):
                engine.submit(command)
        rows.append(engine.evaluator_truth())
        engine.sample_audit.clear()
    events = [asdict(e) for e in engine.truth_events if e.at_us >= start]
    metrics = {'max_mass_error_mL': max((abs(r['mass_error']) for r in rows)), 'root_min_mmHg': min((r['p_root'] for r in rows)), 'root_max_mmHg': max((r['p_root'] for r in rows)), 'max_balloon_mL': max((r['v_balloon'] for r in rows)), 'net_aortic_volume_mL': sum(((a['q_ao'] + b['q_ao']) * 0.0005 for a, b in zip(rows, rows[1:]))), 'lv_net_external_work_mmHg_mL': sum((-(a['p_lv'] + b['p_lv']) / 2 * (b['v_lv'] - a['v_lv']) for a, b in zip(rows, rows[1:])))}
    return {'rows': rows, 'samples': [asdict(s) for s in samples], 'events': events, 'command_log': [asdict(s) for s in engine.command_log], 'metrics': metrics}

def main() -> None:
    out = Path('artifacts/demo')
    out.mkdir(parents=True, exist_ok=True)
    e = Engine(model_config=ModelConfig(balloon_enabled=True))
    add_sinus_schedule(e, 24000000)
    for t in range(0, 18000001, 1000):
        e.advance_to(t)
        e.sample_audit.clear()
    snapshot = e.snapshot()
    cases = {key: record(Engine.from_snapshot(snapshot), 22000000, assist) for key, assist in [('baseline', False), ('assisted', True)]}
    assert cases['baseline']['rows'][0] == cases['assisted']['rows'][0]
    for name, case in cases.items():
        with (out / f'{name}_truth.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(case['rows'][0]))
            writer.writeheader()
            writer.writerows(case['rows'])
        with (out / f'{name}_samples.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(case['samples'][0]))
            writer.writeheader()
            writer.writerows(case['samples'])
        (out / f'{name}_events.json').write_text(json.dumps(case['events'], indent=2), encoding='utf-8')
        (out / f'{name}_commands.json').write_text(json.dumps(case['command_log'], indent=2), encoding='utf-8')
    provenance = {'version': __version__, 'kind': 'ENGINEERING_SIMULATION_NOT_CLINICAL', 'warmup_s': 18, 'note': 'Fixed warmup is NOT proof of periodic steady state.', 'model_config': asdict(e.model.config), 'engine_config': asdict(e.config), 'controller': 'ThresholdDemoController; causal, uncalibrated, not optimized', 'sensors': [asdict(s.config) for s in e._sensors], 'model_source_sha256': hashlib.sha256(Path('iabp/model.py').read_bytes()).hexdigest(), 'metrics': {k: c['metrics'] for k, c in cases.items()}}
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    write_viewer(out / 'prototype_viewer.html', cases, provenance)
    print(json.dumps(provenance['metrics'], indent=2))
    print('Created', out / 'prototype_viewer.html')
if __name__ == '__main__':
    main()
