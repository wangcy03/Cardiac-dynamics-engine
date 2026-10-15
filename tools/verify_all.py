"""Run the reproducible local verification gates and record absent tools honestly."""
from pathlib import Path
import importlib.util
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET


def main() -> None:
    out = Path('artifacts')
    out.mkdir(exist_ok=True)
    jobs = {
        'compile': [sys.executable, '-m', 'compileall', '-q', 'iabp', 'tools', 'examples'],
        'pytest': [sys.executable, '-m', 'pytest', '-q', '--junitxml=artifacts/pytest.xml'],
        'numerical': [sys.executable, '-m', 'tools.numerical_check'],
    }
    results = {}
    for name, cmd in jobs.items():
        run = subprocess.run(cmd, text=True, capture_output=True)
        (out/f'{name}.log').write_text(run.stdout+run.stderr, encoding='utf-8')
        results[name] = {'status': 'PASS' if run.returncode == 0 else 'FAIL', 'command': cmd}
    for tool, args in [('ruff',['check','iabp','tests','tools','examples']), ('mypy',['iabp'])]:
        if importlib.util.find_spec(tool) is None:
            results[tool] = {'status':'NOT_RUN','reason':'tool unavailable; install dev dependencies in target environment'}
        else:
            cmd = [sys.executable,'-m',tool,*args]
            run = subprocess.run(cmd,text=True,capture_output=True)
            (out/f'{tool}.log').write_text(run.stdout+run.stderr,encoding='utf-8')
            results[tool] = {'status':'PASS' if run.returncode == 0 else 'FAIL','command':cmd}
    root = ET.parse(out/'pytest.xml').getroot()
    suites = root.findall('testsuite')
    counts = {key: sum(int(s.attrib.get(key,0)) for s in suites)
              for key in ['tests','failures','errors','skipped']}
    summary = {'release':'r2 / 0.2.0', 'python':sys.version, 'platform':platform.platform(),
               'gates':results,'pytest_counts':counts,'physiological_validation':'NOT_VALIDATED',
               'spatial_convergence':'NOT_IMPLEMENTED','actuator_calibration':'NOT_VALIDATED',
               'real_algorithm_integration':'NOT_IMPLEMENTED', 'github_ci':'NOT_RUN',
               'windows_execution':'NOT_RUN', 'clinical_5ms_claim':'NOT_ESTABLISHED'}
    (out/'verification_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    if any(g['status']=='FAIL' for g in results.values()):
        raise SystemExit(1)

if __name__=='__main__':
    main()
