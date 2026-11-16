"""Record positive planner paths from the full regression suite and bridge checks."""
import functools
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fanxiu_assistant.policy import Planner
from fanxiu_assistant.task_catalog import TASK_ORDER
from fanxiu_assistant.verification import source_fingerprint


def main():
    coverage = {kind: {'calls': 0, 'positive': 0} for kind in TASK_ORDER}
    for kind in TASK_ORDER:
        original = getattr(Planner, 'plan_' + kind)
        def wrap(method, task):
            @functools.wraps(method)
            def invoke(self, *args, **kwargs):
                coverage[task]['calls'] += 1
                result = method(self, *args, **kwargs)
                if result is not None:
                    coverage[task]['positive'] += 1
                return result
            return invoke
        setattr(Planner, 'plan_' + kind, wrap(original, kind))
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful()
    missing = [kind for kind, row in coverage.items() if not row['positive']]
    assert not missing, missing
    validation, bridge_checks, session_checks = [], 0, 0
    for tool in ('check_bridge.py', 'test_bridge.py', 'test_bridge_session.py'):
        run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'tools' / tool)],
                             cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
        output = run.stdout + run.stderr
        assert 'SCRIPT ERROR' not in output and 'Parse Error' not in output
        match = re.search(r'BRIDGE_SAFETY_CHECKS=(\d+) FAILURES=0', output)
        if match:
            bridge_checks = int(match.group(1))
        session_match = re.search(r'SESSION_UPGRADE_CHECKS=(\d+) FAILURES=\[\]', output)
        if session_match: session_checks = int(session_match.group(1))
        validation.append({'tool': tool, 'code': run.returncode, 'output': output})
    for script in ('app.js', 'inventory.js', 'project-info.js'):
        subprocess.run(['node', '--check', str(ROOT / 'web' / script)], check=True)
    report = {'status': 'PASS', 'source_fingerprint': source_fingerprint(ROOT),
              'python_tests': result.testsRun, 'bridge_checks': bridge_checks, 'session_upgrade_checks': session_checks,
              'positive_task_paths': len(coverage), 'task_count': len(TASK_ORDER), 'plans': coverage,
              'bridge_validation': validation, 'real_game_mutations': 0}
    target = ROOT / 'runtime/exe-validation/quick-regression.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('plans', 'bridge_validation')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
