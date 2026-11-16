"""Read-only resource and growth evidence; never stores sessions or credentials."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.monitor import fetch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=1800)
    args = parser.parse_args()
    target = ROOT / '.private/growth-live-evidence.jsonl'
    end = time.monotonic() + args.seconds
    with target.open('a', encoding='utf-8') as output:
        while True:
            s = fetch()
            state = s['state']
            row = {'time': time.time(), 'version': s['app_version'], 'enabled': s['enabled'],
                   'level': state.get('character', {}).get('level'), 'stats': s.get('stats'),
                   'refine': s.get('growth', {}).get('refine'),
                   'owned_items': state.get('owned_items'), 'bound_items': state.get('bound_items'),
                   'breakthrough': s.get('breakthrough_preparation'),
                   'growth_message': s.get('growth', {}).get('message')}
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
            output.flush()
            if time.monotonic() >= end:
                break
            time.sleep(min(10, end - time.monotonic()))
    print(str(target))


if __name__ == '__main__':
    main()
