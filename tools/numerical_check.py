"""Reproducible time-step study of the 0D baseline; not a spatial or patient validation."""
from __future__ import annotations
import json
from pathlib import Path
from time import perf_counter
from iabp.engine import Engine, EngineConfig
from iabp.scenarios import add_sinus_schedule

def run(step_us: int, seconds: int=12) -> dict:
    e = Engine(EngineConfig(step_us=step_us), sensors=())
    add_sinus_schedule(e, seconds * 1000000)
    rows = []
    mass = 0.0
    start = perf_counter()
    for t in range(0, seconds * 1000000 + 1, 1000):
        e.advance_to(t)
        mass = max(mass, abs(e.model.observe()['mass_error']))
        if t >= 9000000:
            rows.append(e.evaluator_truth())
    return {'step_us': step_us, 'rows': rows, 'events': [x for x in e.truth_events if x.at_us >= 9000000], 'max_abs_mass_error_mL': mass, 'wall_seconds': perf_counter() - start}

def evaluate() -> dict:
    runs = [run(x) for x in (250, 125, 50)]
    reference = runs[-1]
    comparisons = []
    for r in runs[:-1]:
        pressure = {key: max((abs(a[key] - b[key]) for a, b in zip(r['rows'], reference['rows']))) for key in ('p_lv', 'p_root', 'p_descending', 'p_la')}
        events = {}
        topology = True
        for name in ('AORTIC_OPEN_05', 'AORTIC_CLOSE_02', 'MITRAL_OPEN_05', 'MITRAL_CLOSE_02', 'DP_LV_AO_REVERSE', 'QAO_ZERO'):
            a = [e.at_us for e in r['events'] if e.name == name]
            b = [e.at_us for e in reference['events'] if e.name == name]
            if len(a) != len(b) or not a:
                topology = False
                events[name] = None
            else:
                events[name] = max((abs(x - y) / 1000 for x, y in zip(a, b)))
        good = topology and max(pressure.values()) <= 0.5 and (max((x for x in events.values() if x is not None)) <= 0.5)
        comparisons.append({'step_us': r['step_us'], 'reference_us': 50, 'pressure_max_difference_mmHg': pressure, 'event_max_difference_ms': events, 'event_topology_match': topology, 'status': 'PASS_0D_BASELINE_TIME_ONLY' if good else 'FAIL'})
    return {'scope': '12 s unassisted engineering baseline; compare at equal times 9-12 s; no temporal alignment', 'model': '0D prototype; no spatial convergence or physiological validation', 'runs': [{k: v for k, v in r.items() if k not in ('rows', 'events')} for r in runs], 'comparisons': comparisons}
if __name__ == '__main__':
    result = evaluate()
    target = Path('artifacts/numerical_check.json')
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    if any((x['status'] == 'FAIL' for x in result['comparisons'])):
        raise SystemExit(1)
