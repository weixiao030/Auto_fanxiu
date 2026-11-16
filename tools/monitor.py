"""Observe a live run using wall-clock time and write a sanitized acceptance record."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request
import hashlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fanxiu_assistant.verification import source_fingerprint
from fanxiu_assistant.server import MIN_BRIDGE_REVISION
from fanxiu_assistant.protection import trade_preserved, locked
from fanxiu_assistant.local_http import open_local
from fanxiu_assistant.flow_evidence import assess_flow
URL = 'http://127.0.0.1:17321'

def fetch():
    with open_local(URL + '/api/status', timeout=5) as response:
        return json.load(response)

def summarize(s):
    c=s.get('state', {}).get('character', {})
    return {'time':datetime.now(timezone.utc).isoformat(), 'connected':s.get('connected'),
            'app_version':s.get('app_version'), 'enabled':s.get('enabled'), 'pid':s.get('pid'), 'revision':s.get('state', {}).get('bridge_revision'),
            'ready':s.get('state', {}).get('ready'), 'network_blocked':s.get('state', {}).get('network_blocked'),
            'level':c.get('level'), 'exp':c.get('exp'), 'wuxing':c.get('wuxing'),
            'cleared':len(s.get('state', {}).get('progress', {}).get('cleared_ids', [])),
            'pending':s.get('pending', {}).get('kind') if s.get('pending') else None,
            'pending_seconds':s.get('pending_seconds', 0), 'stats':s.get('stats', {}),
            'steam_protection':s.get('config', {}).get('preserve_steam_tradable'),
            'steam_inventory':s.get('state', {}).get('steam_inventory'),
            'protection':s.get('config', {}).get('preserve_tradable'),
            'reason':s.get('reason'), 'world_points':s.get('state', {}).get('world', {}).get('point_count'),
            'pending_event':s.get('state', {}).get('world', {}).get('pending_event')}

def event_identity(event):
    if event.get('operation_id'):
        return (event.get('run_id'), event.get('operation_sequence'), event['operation_id'])
    return (event.get('time'), event.get('message'))


def fresh_events(status, seen):
    for event in reversed(status.get('events', [])):
        key = event_identity(event)
        if key not in seen:
            seen.add(key)
            yield event


class BehaviorGuard:
    """Detect recurring protocol mistakes while allowing normal combat loss/backoff."""
    def __init__(self):
        self.seen = set()
        self.failures = {}
        self.stronghold_attempts = {}
        self.pending_event = None
        self.pending_since = None

    def inspect(self, status, elapsed):
        problems = []
        state = status.get('state', {})
        event = state.get('world', {}).get('pending_event') or {}
        if event and event.get('type') not in ('cultivator_help', 'senior_cultivator'):
            problems.append('已结算的普通奇遇阻塞探索')
        identity = (event.get('type'), event.get('event_id')) if event else None
        if identity != self.pending_event:
            self.pending_event = identity
            self.pending_since = elapsed if identity else None
        if (identity and status.get('config', {}).get('tasks', {}).get('world_events')
                and elapsed - self.pending_since > 180):
            problems.append('同一奇遇超过180秒未能处理')
        # A stronghold needs a discovery call and a selection call, not endless discovery.
        pending_markers = {int(p['marker_id']) for p in state.get('world', {}).get('points', [])
                           if p.get('type') == 'stronghold' and p.get('choices') and p.get('marker_id')}
        for marker in list(self.stronghold_attempts):
            if marker not in pending_markers:
                self.stronghold_attempts.pop(marker)
        for row in reversed(status.get('events', [])):
            key = (row.get('time'), row.get('message'))
            if key in self.seen:
                continue
            self.seen.add(key)
            kind = row.get('kind')
            if row.get('level') == 'success':
                marker = row.get('marker_id')
                if kind == 'world_points' and marker and int(marker) in pending_markers:
                    marker = int(marker)
                    self.stronghold_attempts[marker] = self.stronghold_attempts.get(marker, 0) + 1
                    if self.stronghold_attempts[marker] >= 4:
                        problems.append('据点重复读取候选奖励，未完成领奖')
                self.failures.pop(kind, None)
                continue
            message = row.get('message', '')
            if kind and any(reason in message for reason in (
                    '事件不存在或已处理', '缺少预期结果', '战斗未能开始', '操作长时间未确认', '挑战结算未确认')):
                self.failures[kind] = self.failures.get(kind, 0) + 1
                if self.failures[kind] >= 3:
                    problems.append(f'{kind}连续出现3次无效操作')
        return problems


def main(seconds=1800, period=10, candidate_dir=None, continue_on_failure=False):
    if seconds < 1800:
        raise SystemExit('正式验收至少需要1800秒，不能缩短或折算时间')
    initial=fetch();first=summarize(initial)
    if (not first['connected'] or not first['ready'] or first['revision'] < MIN_BRIDGE_REVISION
            or (not first['enabled'] and not (continue_on_failure and first['network_blocked']))):
        raise SystemExit('等待新版桥接连接并开始自动化后，再启动正式验收')
    candidate=Path(candidate_dir or ROOT/'.private/release-steam')
    build=json.loads((candidate/'build-info.json').read_text(encoding='utf8'))
    exe=candidate/build['file']
    if source_fingerprint(ROOT)!=build['source_fingerprint'] or hashlib.sha256(exe.read_bytes()).hexdigest()!=build['sha256'] or initial.get('app_version')!=build['app_version']:
        raise SystemExit('运行版本、源码与候选EXE不一致')
    command="[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $owner=(Get-NetTCPConnection -LocalPort 17321 -State Listen).OwningProcess; Get-CimInstance Win32_Process -Filter ('ProcessId = '+$owner) | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"
    owner=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',command],encoding='utf-8-sig'))
    if Path(owner['ExecutablePath']).resolve()!=exe.resolve():raise SystemExit('当前服务不是候选EXE')
    steam=initial['state'].get('steam_inventory',{})
    if initial['config'].get('preserve_steam_tradable') and not (steam.get('complete') and steam.get('catalogue_ready')):raise SystemExit('等待真实Steam库存与定义读取完成')
    run=ROOT/'runtime'/('acceptance-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    run.mkdir(parents=True)
    baseline={int(e['id']) for e in initial['state'].get('equipment', []) if e.get('locked') or locked(initial['config'],'equipment',int(e['id']))}
    tradable={int(e['id']) for e in initial['state'].get('equipment', []) if e.get('bound') is not True and trade_preserved(initial['config'],'equipment',e)}
    inventory=initial['state'].get('inventory_view',{})
    preserved={row['key']:int(row['count'])-int(row.get('bound_count',0)) for row in inventory.get('items',[]) if trade_preserved(initial['config'],row['kind'],row) and int(row['count'])>int(row.get('bound_count',0))}
    fixed={row['key']:int(row['count']) for row in inventory.get('items',[]) if locked(initial['config'],row['kind'],int(row['id']),row.get('layer'))}
    protection_settings={k:initial['config'].get(k) for k in ('preserve_steam_tradable','preserve_tradable','trade_rules','manual_locks','protected_equipment')}
    inventory_generation=inventory.get('generation')
    inventory_updates={inventory.get('updated_at')}
    fingerprint=source_fingerprint(ROOT)
    log=Path.home()/'AppData/Roaming/Godot/app_userdata/凡修/logs/godot.log'
    log_offset=log.stat().st_size if log.exists() else 0
    guard=BehaviorGuard()
    guard.seen={(e.get('time'),e.get('message')) for e in initial.get('events', [])}
    start=time.monotonic();previous=start;deadline=start+seconds;lost_since=None;failures=[];samples=0;seen_events={event_identity(e) for e in initial.get('events', [])};flow_events=[];last=first
    print(json.dumps({'record':str(run),'started':first['time'],'required_seconds':seconds},ensure_ascii=False),flush=True)
    with (run/'samples.jsonl').open('a',encoding='utf8') as out, (run/'events.jsonl').open('a',encoding='utf8') as events:
        while True:
            now=time.monotonic()
            if now-previous>period+30: failures.append('采样中断，不能证明连续监控')
            previous=now
            try:
                s=fetch();last=summarize(s);last['elapsed_seconds']=round(now-start,1)
                out.write(json.dumps(last,ensure_ascii=False)+'\n');out.flush();samples+=1
                for event in fresh_events(s, seen_events):
                    flow_events.append(event)
                    events.write(json.dumps(event,ensure_ascii=False)+'\n')
                events.flush()
                failures.extend(guard.inspect(s,now-start))
                if last['app_version'] != first['app_version']:failures.append('验收期间助手版本变化')
                if last['revision'] != first['revision']:failures.append('验收期间桥接版本变化')
                if not last['ready']:failures.append('游戏未处于可运行状态')
                if not last['connected']:
                    lost_since=lost_since or now
                    if now-lost_since>30:failures.append('游戏桥接连续断开超过30秒')
                else:lost_since=None
                if not last['enabled']:failures.append('自动化意外暂停')
                if last['network_blocked']:failures.append('游戏会话被阻断')
                if last['pid']!=first['pid']:failures.append('验收期间游戏进程发生变化')
                if last['pending_seconds']>330:failures.append('操作长时间未确认')
                ids={int(e['id']) for e in s.get('state',{}).get('equipment',[])}
                if baseline-ids:failures.append('锁定或手动保护的装备消失')
                if tradable-ids:failures.append('开启保留期间原有可交易或绑定未知的装备消失')
                if initial['config']['preserve_tradable'] and not last['protection']:failures.append('验收期间关闭了交易保护')
                if any(s['config'].get(k)!=v for k,v in protection_settings.items()):failures.append('验收期间物品保留规则或固定锁发生变化')
                view=s['state'].get('inventory_view',{})
                inventory_updates.add(view.get('updated_at'))
                rows={row['key']:row for row in view.get('items',[])}
                for key,quantity in preserved.items():
                    row=rows.get(key,{})
                    if int(row.get('count',0))-int(row.get('bound_count',0))<quantity:failures.append('交易保留范围内的未绑定库存减少：'+key)
                for key,quantity in fixed.items():
                    if int(rows.get(key,{}).get('count',0))<quantity:failures.append('固定锁库存减少：'+key)
                if s['config'].get('inventory_auto_refresh') and view.get('updated_at') and time.time()-view['updated_at']>s['config']['inventory_refresh_seconds']+30:failures.append('背包自动刷新超时')
                if source_fingerprint(ROOT)!=fingerprint:failures.append('验收期间分发源代码发生变化，需重新计时')
                if log.exists():
                    if log.stat().st_size<log_offset:failures.append('游戏日志在验收期间被重建')
                    with log.open('rb') as stream:
                        stream.seek(log_offset);raw=stream.read();log_offset=stream.tell()
                    if b'SCRIPT ERROR' in raw or b'Parse Error' in raw:failures.append('游戏产生脚本错误')
            except (OSError, ValueError, TimeoutError) as error:
                lost_since=lost_since or now
                out.write(json.dumps({'elapsed_seconds':round(now-start,1),'read_error':type(error).__name__,'detail':str(error)},ensure_ascii=False)+'\n');out.flush()
                if now-lost_since>30:failures.append('本机控制台连续不可读超过30秒')
            if (failures and not continue_on_failure) or now>=deadline:break
            time.sleep(min(period,max(0,deadline-time.monotonic())))
    elapsed=time.monotonic()-start
    if not failures and last['stats'].get('success',0)<=first['stats'].get('success',0):failures.append('期间没有已确认的成功操作')
    failures = list(dict.fromkeys(failures))
    result={'status':'FAIL' if failures else 'PASS', 'continue_on_failure':continue_on_failure, 'elapsed_seconds':round(elapsed,2), 'required_seconds':seconds,
            'samples':samples,'started':first['time'],'finished':datetime.now(timezone.utc).isoformat(),
            'initial':first,'final':last,'failures':failures,'protected_equipment_checked':len(baseline),
            'tradable_equipment_checked':len(tradable),'preserved_unbound_item_types_checked':len(preserved),'fixed_item_types_checked':len(fixed),'inventory_refreshes':len(inventory_updates),'source_fingerprint':fingerprint,
            'exe_sha256':build['sha256'],'app_version':build['app_version'],'assistant_process':owner['ProcessId'],'steam_initial':steam,
            'game_version':initial.get('state',{}).get('version')}
    result['growth_flow'] = assess_flow(flow_events, started=result['started'], finished=result['finished'], revision=first['revision'])
    (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return int(bool(failures))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=1800);parser.add_argument('--period',type=float,default=10)
    parser.add_argument('--candidate-dir',type=Path)
    parser.add_argument('--continue-on-failure', action='store_true',
                        help='记录异常后仍采满观察窗口；任何失败仍判FAIL，不能用于稳定发布')
    args=parser.parse_args()
    if args.period<=0 or args.period>60:parser.error('采样间隔需在0至60秒之间')
    raise SystemExit(main(args.seconds,args.period,args.candidate_dir,args.continue_on_failure))
