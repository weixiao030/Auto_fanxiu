"""Seal an observed live window when a user shortens an already running monitor.

The original validator must still be alive: it exits immediately on a guard
failure. Its full record remains untouched and continues independently.
"""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fanxiu_assistant.verification import source_fingerprint
from fanxiu_assistant.server import MIN_BRIDGE_REVISION
from tools.monitor import fetch, summarize


def review(rows, minimum=1800):
    if minimum < 1800 or len(rows) < 2:
        raise ValueError('至少需要1800秒的真实连续样本')
    first, last = rows[0], rows[-1]
    if first.get('elapsed_seconds', 999) > 1 or last.get('elapsed_seconds', 0) < minimum:
        raise ValueError('样本尚未覆盖要求的连续时长')
    previous = first
    for row in rows:
        if row.get('read_error'):
            raise ValueError('检查点要求所有样本均可读')
        if any(row.get(k) is not True for k in ('connected', 'enabled', 'ready', 'protection')):
            raise ValueError('连接、自动化、就绪或交易保护中断')
        if row.get('network_blocked') or row.get('pid') != first.get('pid') or row.get('revision') != first.get('revision') or first.get('revision', 0) < MIN_BRIDGE_REVISION:
            raise ValueError('会话、进程或桥接版本发生变化')
        gap = row['elapsed_seconds'] - previous['elapsed_seconds']
        wall_gap = (datetime.fromisoformat(row['time']) - datetime.fromisoformat(previous['time'])).total_seconds()
        if not 0 <= gap <= 40 or abs(wall_gap-gap) > 2 or row.get('pending_seconds', 0) > 330:
            raise ValueError('采样中断或操作未确认')
        previous = row
    if last['stats'].get('success', 0) <= first['stats'].get('success', 0):
        raise ValueError('期间没有游戏确认的成功操作')
    return first, last


def validator_alive(pid):
    # Query only the explicitly named validator, not unrelated process arguments.
    command = f"Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    value = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, text=True, check=True)
    process = json.loads(value.stdout or 'null')
    return bool(process and 'tools/monitor.py' in process.get('CommandLine', '') and '--seconds 1800' in process.get('CommandLine', ''))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('record', type=Path)
    parser.add_argument('--monitor-pid', type=int, required=True)
    args = parser.parse_args()
    record = args.record.resolve()
    if not validator_alive(args.monitor_pid):
        raise SystemExit('原始实时校验器已停止，不可生成进行中检查点')
    rows = [json.loads(line) for line in (record/'samples.jsonl').read_text(encoding='utf-8').splitlines() if line]
    first, last = review(rows)
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(last['time'])).total_seconds()
    if not 0 <= age <= 40:
        raise SystemExit('样本已过期')
    started = datetime.fromisoformat(first['time']).timestamp()
    files = [*ROOT.joinpath('fanxiu_assistant').rglob('*.py'), *ROOT.joinpath('bridge').glob('*.gd'),
             *ROOT.joinpath('web').glob('*'), ROOT/'desktop_entry.py']
    if any(p.stat().st_mtime > started for p in files if p.is_file()):
        raise SystemExit('分发源代码在观测期间发生变化')
    current = fetch()
    now = summarize(current)
    now['elapsed_seconds'] = last['elapsed_seconds'] + age
    review([*rows, now])
    if not validator_alive(args.monitor_pid):
        raise SystemExit('原始校验器已结束，请改用其最终结果')
    result_path = record/'result.json'
    if result_path.exists() and json.loads(result_path.read_text(encoding='utf-8')).get('status') != 'PASS':
        raise SystemExit('原始校验器报告失败')
    result = {'status':'PASS', 'required_seconds':1800, 'elapsed_seconds':last['elapsed_seconds'],
              'samples':len(rows), 'started':first['time'], 'finished':last['time'],
              'initial':first, 'final':last, 'failures':[], 'game_version':current['state']['version'],
              'source_fingerprint':source_fingerprint(ROOT),
              'evidence_kind':'checkpoint_of_active_live_validator', 'validator_pid':args.monitor_pid,
              'original_monitor_continues':True,
              'guard_scope':'原实时校验器持续检查物品保护、脚本错误、协议停滞及源码指纹；失败立即结束。',
              'coverage_limit':'仅证明该角色与当次策略的连续运行，不代表所有玩法分支均已实机触发。'}
    target = record/'checkpoint-30min.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(target),'elapsed_seconds':result['elapsed_seconds'],'samples':len(rows)},ensure_ascii=False))


if __name__ == '__main__':
    main()
