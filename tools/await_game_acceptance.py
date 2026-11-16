"""Wait for the existing client to enter, then run the unchanged 30-minute check.

Only reads local assistant status. Never cancels queues, restarts games, or logs in.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.monitor import fetch
from fanxiu_assistant.verification import source_fingerprint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-dir', type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate_dir.resolve()
    build = json.loads((candidate / 'build-info.json').read_text(encoding='utf-8'))
    target = ROOT / 'runtime/await-game-acceptance.json'

    def record(phase, **data):
        row = {'phase': phase, 'updated': datetime.now(timezone.utc).isoformat(),
               'app_version': build['app_version'], 'bridge_revision': build['bridge_revision'],
               'source_fingerprint': build['source_fingerprint'], **data}
        temporary = target.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(target)
        return row

    previous_phase, unavailable_since = None, None
    while True:
        if source_fingerprint(ROOT) != build['source_fingerprint']:
            raise RuntimeError('候选源码已变化，不能沿用待验任务')
        try:
            status = fetch()
            unavailable_since = None
            if status.get('app_version') != build['app_version']:
                raise RuntimeError('运行助手版本已变化，停止旧候选待验任务')
            state = status.get('state', {})
            steam = state.get('steam_inventory', {})
            inventory_ready = (not status.get('config', {}).get('preserve_steam_tradable')
                               or (steam.get('complete') and steam.get('catalogue_ready')))
            ready = (inventory_ready and status.get('connected') and state.get('ready') and not state.get('network_blocked') and status.get('enabled')
                     and state.get('bridge_revision') == build['bridge_revision'])
            phase = 'READY' if ready else 'WAITING_FOR_NATIVE_CLIENT'
            row = record(phase, connected=status.get('connected'), enabled=status.get('enabled'),
                         ready=state.get('ready'), readiness=state.get('readiness'), inventory_ready=bool(inventory_ready),
                         pid=status.get('pid'), bridge_revision=state.get('bridge_revision'),
                         note='等待当前原生客户端进入角色；不取消队列、不重新登录、不重开游戏')
            if phase != previous_phase:
                print(json.dumps(row, ensure_ascii=False), flush=True)
                previous_phase = phase
            if ready:
                break
        except (OSError, ValueError, TimeoutError) as error:
            unavailable_since = unavailable_since or time.monotonic()
            record('LOCAL_SERVICE_UNAVAILABLE', error=type(error).__name__)
            if time.monotonic() - unavailable_since >= 90:
                raise RuntimeError('本机状态连续不可读，未启动验收') from error
        time.sleep(1)

    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    record('MONITORING', required_seconds=1800)
    monitor = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'tools/monitor.py'),
                                '--seconds', '1800', '--period', '10', '--candidate-dir', str(candidate)],
                               cwd=ROOT, creationflags=flags)
    interface = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'tools/validate_growth_ui.py')],
                               cwd=ROOT, creationflags=flags)
    if interface.returncode:
        record('INTERFACE_FAILED_MONITORING_CONTINUES', interface_exit_code=interface.returncode)
    monitor_code = monitor.wait()
    record('MONITOR_PASS' if monitor_code == 0 else 'MONITOR_FAILED',
           required_seconds=1800, monitor_exit_code=monitor_code,
           note='完整结果见runtime/acceptance-*/result.json；此工具不生成正式发布包')
    return monitor_code


if __name__ == '__main__':
    raise SystemExit(main())
