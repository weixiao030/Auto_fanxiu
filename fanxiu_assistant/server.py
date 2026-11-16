from __future__ import annotations
import argparse
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit
from .policy import Planner, DEFAULTS, LABELS, QUALITIES, CONFIG_FIELDS, validate_config

from .paths import ROOT, RUNTIME, INVENTORY_ICONS

from .connection import HEARTBEAT_FRESH_SECONDS, CONNECTION_TIMEOUT_SECONDS
from .protection import CATEGORIES, valid_lock, command_keys, keys_overlap
from .version import APP_TITLE, VERSION
from .diagnostics import execution_status
from .readiness import waiting_message
from .flow_evidence import sanitize_receipt
from .outcomes import failure_metadata, result_detail

MIN_BRIDGE_REVISION = 45


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def edited_config(current, packet):
    """Merge a single explicit edit into the latest config under the controller lock."""
    if not isinstance(packet, dict):
        raise ValueError('配置请求必须为对象')
    if set(packet) == {'replace'}:
        return validate_config(packet['replace'])
    if set(packet) != {'edit'} or not isinstance(packet['edit'], dict) or set(packet['edit']) != {'path', 'value'}:
        raise ValueError('旧版网页不能保存整份配置，请刷新页面后重试')
    edit = packet['edit']
    path = edit['path']
    if not isinstance(path, list) or not 1 <= len(path) <= 3 or any(not isinstance(part, str) for part in path):
        raise ValueError('配置字段路径无效')
    candidate = deepcopy(current)
    target = candidate
    for part in path[:-1]:
        if not isinstance(target, dict) or part not in target or not isinstance(target[part], dict):
            raise ValueError('配置字段路径无效')
        target = target[part]
    if not isinstance(target, dict) or path[-1] not in target:
        raise ValueError('配置字段不存在')
    target[path[-1]] = deepcopy(edit['value'])
    return validate_config(candidate)


class Controller:
    def __init__(self):
        RUNTIME.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.planner = Planner()
        self.key_path = RUNTIME / 'bridge.key'
        if not self.key_path.exists():
            self.key_path.write_text(secrets.token_hex(32), encoding='utf-8')
        self.key = self.key_path.read_text(encoding='utf-8').strip()
        config_path = RUNTIME / 'config.json'
        if config_path.exists():
            self.planner.config = validate_config(json.loads(config_path.read_text(encoding='utf-8')))
        else:
            atomic_json(config_path, self.planner.config)
        legacy={f'equipment:{eid}' for eid in self.planner.config['protected_equipment']}
        if legacy-set(self.planner.config['manual_locks']):
            self.planner.config['manual_locks']=sorted(set(self.planner.config['manual_locks'])|legacy)
            atomic_json(config_path,self.planner.config)
        self.enabled = False
        self.resume_requested = False
        self.maintenance = {}
        self.state = {}
        self.last_seen = 0
        self.pid = None
        self.pending = None
        self.pending_at = 0
        self.pending_sent = False
        self.manual = False
        self.manual_queue = deque()
        self.task_feedback = {}
        self.inventory_generation = 1
        self.daily_path = RUNTIME / "daily.json"
        self.daily = json.loads(self.daily_path.read_text(encoding="utf-8")) if self.daily_path.exists() else {}
        self.capture_path = RUNTIME / 'capture-actions.json'
        self.capture_actions = json.loads(self.capture_path.read_text(encoding='utf-8')) if self.capture_path.exists() else {}
        self.completed = deque(maxlen=1000)
        self.events = deque(maxlen=250)
        self.stats = Counter()
        self.operation_run = secrets.token_hex(12)
        self.operation_sequence = 0
        self.started = None
        self.csrf = secrets.token_urlsafe(24)
        self.log('info', '控制台已启动，等待游戏内桥接连接')

    def log(self, level, message, **extra):
        event = {'time': datetime.now(timezone.utc).isoformat(), 'level': level, 'message': message, **extra}
        self.events.appendleft(event)
        with (RUNTIME / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')

    def public(self):
        age = time.monotonic() - self.last_seen
        connected = self.pid is not None and age < CONNECTION_TIMEOUT_SECONDS
        connection_state = 'connected' if connected and age < HEARTBEAT_FRESH_SECONDS else 'recovering' if connected else 'disconnected'
        return {'connected': connected, 'pid': self.pid if connected else None, 'enabled': self.enabled,
                'connection': {'state': connection_state, 'heartbeat_age_seconds': round(age, 1) if self.pid is not None else None},
                'execution': execution_status(self.state, self.planner.config, connected=connected,
                    heartbeat_age=age, enabled=self.enabled, pending=self.pending,
                    pending_seconds=time.monotonic()-self.pending_at if self.pending else 0,
                    retry_after=max(0, self.planner.server_busy_until-self.planner.clock()),
                    minimum_revision=MIN_BRIDGE_REVISION, resume_requested=self.resume_requested),
                'manual_queue': [{'kind': kind, 'label': LABELS[kind], 'position': i+1} for i,kind in enumerate(self.manual_queue)],
                'task_feedback': dict(self.task_feedback),
                'minimum_bridge_revision': MIN_BRIDGE_REVISION, 'trade_categories': CATEGORIES,
                'inventory_generation': self.inventory_generation, 'app_name':APP_TITLE, 'app_version':VERSION,
                'retry_after_seconds': max(0, round(self.planner.server_busy_until-self.planner.clock(), 1)),
                'task_details': {'synth': self.planner.synthesis_status(self.state), 'breakthrough': self.planner.breakthrough_status(self.state), 'world_explore': self.planner.world_exploration_status(self.state), 'world_points': self.planner.world_points_status(self.state), 'world_events': self.planner.world_events_status(self.state), 'refine': self.planner.refine_status(self.state)},
                'growth': self.planner.growth_status(self.state),
                'state': self.state, 'config': self.planner.config, 'events': list(self.events),
                'maintenance': self.maintenance, 'stats': dict(self.stats), 'pending': self.pending, 'pending_seconds': round(time.monotonic() - self.pending_at, 1) if self.pending else 0,
                'reason': (waiting_message(self.state) if not self.state.get('ready') else self.planner.reason if self.enabled or self.pending else '已暂停，可执行单项任务或开始自动修炼') if connected else '等待游戏内桥接连接',
                'csrf': self.csrf, 'started': self.started, 'labels': LABELS, 'qualities': QUALITIES, 'fields': CONFIG_FIELDS, 'daily': self.daily}

    def bridge(self, packet):
        pid = packet.get('pid')
        if type(pid) is not int or not isinstance(packet.get('state'), dict):
            raise ValueError('Invalid bridge packet')
        if self.pid is not None and self.pid != pid and time.monotonic() - self.last_seen < CONNECTION_TIMEOUT_SECONDS:
            raise ValueError('已有客户端连接，拒绝第二实例')
        if self.pid != pid:
            self.operation_run = secrets.token_hex(12)
            self.operation_sequence = 0
            self.cancel_queue('客户端已更换，已取消未执行的排队任务')
            self.log('info', f'已连接游戏进程 {pid}，沿用客户端会话')
            if self.pending:
                self.enabled = False
                self.resume_requested = False
                self.log('warning', '客户端发生重启，未确认操作需检查后继续')
                self.pending = None
                self.manual = False
                self.pending_sent = False
        self.pid = pid
        self.last_seen = time.monotonic()
        self.state = packet['state']
        if self.state.get('bridge_revision',0)<MIN_BRIDGE_REVISION:
            self.enabled=False
            self.cancel_queue('等待自有桥接更新，保留当前游戏会话')
        day = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).date().isoformat()
        if self.daily.get('day') != day:
            self.daily = {'day': day, 'world_explore': 0}
        if self.state.get('world'):
            free_used = int(self.state['world'].get('free_used', self.state['world'].get('daily_count', 0)))
            self.daily['world_free_observed'] = max(self.daily.get('world_free_observed', 0), free_used)
            self.daily['world_explore'] = max(self.daily.get('world_explore', 0), self.daily['world_free_observed'] + self.daily.get('world_paid', 0))
            self.state['world']['daily_count'] = self.daily['world_explore']
        self.state['assistant_daily'] = self.daily.copy()
        self.state['capture_actions'] = self.capture_actions
        acks = []
        for result in packet.get('results', []):
            rid = result.get('id')
            if not isinstance(rid, str):
                continue
            acks.append(rid)
            if rid in self.completed:
                continue
            self.completed.append(rid)
            if self.pending and rid == self.pending['id']:
                command = self.pending
                self.planner.observe_result(command, result, self.state)
                ok = bool(result.get('ok'))
                if result.get('data', {}).get('unconfirmed'):
                    self.enabled = False
                    self.resume_requested = False
                    self.cancel_queue('上一操作未确认，已取消排队任务')
                    self.log('warning', '服务器未确认战斗结果，已停止自动化，请检查游戏状态')
                self.stats['success' if ok else 'failed'] += 1
                self.stats[command['kind']] += int(ok)
                if command['kind'] == 'world_explore' and ok:
                    data = result.get('data', {})
                    if data.get('exploration_day', day) == day:
                        mode = data.get('exploration_mode')
                        if mode in ('rumor', 'mirror'):
                            self.daily['world_paid'] = self.daily.get('world_paid', 0) + 1
                        elif mode != 'free':  # Legacy acknowledgements lack execution metadata.
                            self.daily['world_explore'] += 1
                        self.daily['world_explore'] = max(self.daily['world_explore'], self.daily.get('world_free_observed', 0) + self.daily.get('world_paid', 0))
                        atomic_json(self.daily_path, self.daily)
                self.manual = False
                self.operation_sequence += 1
                receipt = sanitize_receipt(result.get('data', {}).get('growth_receipt'), command['kind'])
                detail = result_detail(result)
                failure = failure_metadata(result) if not ok else {}
                self.log('success' if ok else 'warning', f'{command["label"]}：{detail}',
                         kind=command['kind'], marker_id=command.get('params', {}).get('marker_id'),
                         operation_id=command['id'], run_id=self.operation_run,
                         operation_sequence=self.operation_sequence, bridge_revision=self.state.get('bridge_revision'),
                         **({'failure': failure} if failure else {}),
                         **({'growth_receipt': receipt} if receipt is not None and ok else {}))
                self.task_feedback[command['kind']] = detail
                if command.get('parent_kind') == 'breakthrough':
                    self.task_feedback['breakthrough'] = command['label'] + '：' + detail
                self.pending = None
                self.pending_sent = False
        if self.state.get('world'):
            self.state['world']['daily_count'] = self.daily.get('world_explore', 0)
        self.state['assistant_daily'] = self.daily.copy()
        if self.state.get('network_blocked') and self.enabled:
            self.enabled = False
            self.log('warning', '游戏会话已暂停；助手停止操作，避免抢登')
        if self.pending and time.monotonic() - self.pending_at > 330:
            self.enabled = False
            self.resume_requested = False
            self.manual = False
            self.planner.reason = '操作结果未确认，已暂停自动化'
            self.cancel_queue('操作结果未确认，已取消排队任务')
        if not self.pending and not packet.get('busy'):
            self.dispatch_manual()
        if self.enabled and not self.pending and not packet.get('busy'):
            self.pending = self.planner.choose(self.state)
            if self.pending:
                self.pending_at = time.monotonic()
                self.pending_sent = False
                self.record_attempt(self.pending)
                self.log('info', self.pending['label'] + '，等待游戏确认', kind=self.pending['kind'])
        command = (self.pending or {}) if (self.enabled or self.manual) else {}
        if command:
            self.pending_sent = True
        return {'acks': acks, 'command': command, 'policy': self.planner.config, 'daily_guard': self.daily.copy(),
                'inventory_request': {'generation':self.inventory_generation,'icon_directory':str((INVENTORY_ICONS).resolve())}}

    def cancel_queue(self, reason):
        for kind in self.manual_queue:
            self.task_feedback[kind] = reason
        self.manual_queue.clear()

    def queue_task(self, kind):
        if kind in self.manual_queue or self.pending and kind in (self.pending.get('kind'), self.pending.get('parent_kind')):
            return {'queued': True, 'message': '该任务已在执行或排队，无需重复提交。'}
        self.manual_queue.append(kind)
        self.task_feedback[kind] = '已排队，当前操作结束后按最新状态复核条件。'
        self.log('info', LABELS[kind]+'：已加入执行队列', kind=kind)
        self.dispatch_manual()
        return {'queued': kind in self.manual_queue, 'message': self.task_feedback[kind]}

    def dispatch_manual(self):
        s = self.state
        if not self.manual_queue or self.pending or time.monotonic()-self.last_seen >= HEARTBEAT_FRESH_SECONDS:
            return
        if self.planner.clock() < self.planner.server_busy_until:
            return
        if s.get('battle') or s.get('battle_pending') or s.get('pending', 0) or s.get('network_blocked'):
            return
        if not s.get('ready') or not s.get('online') or time.monotonic()-self.planner.last_action < self.planner.config['interval']:
            return
        kind = self.manual_queue.popleft()
        old_tasks, old_due = self.planner.config['tasks'], self.planner.due.copy()
        try:
            self.planner.config['tasks'] = {**old_tasks, kind: True}
            self.planner.due[kind] = 0
            command = self.planner.choose(s, only_kind=kind)
        finally:
            self.planner.config['tasks'] = old_tasks
            self.planner.due = old_due
        if not command:
            detail = self.planner.breakthrough_status(s)['message'] if kind == 'breakthrough' else self.planner.synthesis_status(s)['message'] if kind == 'synth' else self.planner.world_exploration_status(s)['message'] if kind == 'world_explore' else self.planner.refine_status(s)['message'] if kind in ('refine','world_forge') else '当前执行条件未满足：检查材料、解锁、保留数量及冷却；自动任务会继续等待条件满足。'
            self.task_feedback[kind] = detail
            self.log('info', LABELS[kind]+'：'+detail, kind=kind)
            return
        command['manual'] = True
        self.pending, self.manual, self.pending_at = command, True, time.monotonic()
        self.pending_sent = False
        self.record_attempt(command)
        self.task_feedback[kind] = '已安排，等待游戏确认。'
        self.log('info', command['label']+'：已安排立即执行', kind=kind)

    def record_attempt(self, command):
        kind=command['kind']; p=command.get('params', {})
        if kind in ('player_capture','player_occupy','bounty_claim'):
            self.daily[kind]=self.daily.get(kind,0)+1
            atomic_json(self.daily_path, self.daily)
        if kind in ('slave_escape','bounty_publish'):
            cid=str(p['capture_id'])
            self.capture_actions.setdefault(cid,{})[p['action'] if kind=='slave_escape' else kind]=True
            # Only opaque capture identifiers, never credentials or player identity.
            self.capture_actions=dict(list(self.capture_actions.items())[-100:])
            atomic_json(self.capture_path,self.capture_actions)

    def stop(self):
        self.resume_requested = False
        self.enabled = False
        self.manual = False
        self.cancel_queue('已暂停并取消排队任务')
        if self.pending and not self.pending_sent:
            self.pending = None
            self.log('info', '已取消尚未提交到游戏的操作')
        self.log('info', '已暂停，当前已提交操作会完成结算')


class Handler(BaseHTTPRequestHandler):
    server_version = 'FanxiuAssistant/0.1'

    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    @property
    def controller(self):
        return self.server.controller

    def response(self, code, data, mime='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8') if mime.startswith('application/json') and not isinstance(data, bytes) else data
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.valid_host():
            return self.response(403, {'error': 'Invalid host'})
        route = urlsplit(self.path).path
        if route == '/api/health':
            return self.response(200, {'service': 'fanxiu-local'})
        with self.controller.lock:
            if route == '/api/status':
                return self.response(200, self.controller.public())
            if route == '/api/export':
                return self.response(200, self.controller.planner.config)
        if route.startswith('/icons/'):
            name=route.removeprefix('/icons/')
            if len(name)!=68 or not name.endswith('.png') or any(c not in '0123456789abcdef' for c in name[:-4]):
                return self.response(404, {'error':'Icon not found'})
            icon=INVENTORY_ICONS/name
            if not icon.is_file() or icon.stat().st_size>1_000_000:return self.response(404, {'error':'Icon not found'})
            return self.response(200,icon.read_bytes(),'image/png')
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/inventory.js': ('inventory.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        files.update({'/project-info.js': ('project-info.js', 'text/javascript; charset=utf-8'), '/project-info.json': ('project-info.json', 'application/json; charset=utf-8'), '/appreciation-code.webp': ('appreciation-code.webp', 'image/webp')})
        if route not in files:
            return self.response(404, {'error': 'Not found'})
        file, mime = files[route]
        path = ROOT / 'web' / file
        if not path.is_file():
            return self.response(404, {'error': 'Not found'})
        return self.response(200, path.read_bytes(), mime)

    def do_POST(self):
        if not self.valid_host():
            return self.response(403, {'error': 'Invalid host'})
        c = self.controller
        route = urlsplit(self.path).path
        if route == '/bridge':
            if not secrets.compare_digest(self.headers.get('X-Bridge-Key', ''), c.key):
                return self.response(403, {'error': 'Bridge authentication failed'})
        else:
            origin = self.headers.get('Origin')
            allowed = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
            if origin not in allowed or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), c.csrf):
                return self.response(403, {'error': '请刷新本地控制台后重试'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 2_000_000:
                raise ValueError('请求过大')
            packet = json.loads(self.rfile.read(size) or b'{}')
            with c.lock:
                if route == '/bridge':
                    return self.response(200, c.bridge(packet))
                if route == '/api/config':
                    config = edited_config(c.planner.config, packet)
                    # Only an explicit click on the lock endpoint can remove a fixed lock.
                    config['manual_locks']=sorted(set(c.planner.config['manual_locks'])|{f'equipment:{eid}' for eid in c.planner.config['protected_equipment']}|{f'equipment:{eid}' for eid in config['protected_equipment']})
                    atomic_json(RUNTIME / 'config.json', config)
                    c.planner.config = config
                    c.log('info', '配置已保存并立即生效')
                    return self.response(200, {'ok': True, 'config': config})
                elif route == '/api/run':
                    if c.state.get('bridge_revision', 0) < MIN_BRIDGE_REVISION:
                        raise ValueError('等待新版桥接连接；请保持当前游戏运行')
                    kind = packet.get('kind')
                    if kind not in LABELS:
                        raise ValueError('未知功能')
                    if time.monotonic() - c.last_seen >= CONNECTION_TIMEOUT_SECONDS:
                        raise ValueError('游戏连接正在恢复，请等候心跳同步')
                    return self.response(200, c.queue_task(kind))
                elif route == '/api/cancel-run':
                    kind = packet.get('kind')
                    if kind in c.manual_queue:
                        c.manual_queue.remove(kind)
                        c.task_feedback[kind] = '已取消排队任务'
                    return self.response(200, {'message': '已取消排队，已提交的操作仍正常结算。'})
                elif route == '/api/inventory/refresh':
                    c.inventory_generation+=1
                    return self.response(200,{'message':'已请求读取当前游戏背包，不会消耗物品。','generation':c.inventory_generation})
                elif route == '/api/lock':
                    key=packet.get('key');value=packet.get('locked')
                    if not valid_lock(key) or type(value) is not bool:raise ValueError('固定锁参数无效')
                    if value and c.pending and c.pending_sent and any(keys_overlap(key,used) for used in command_keys(c.pending['kind'],c.pending.get('params',{}),c.state)):
                        return self.response(409,{'error':'该物品的操作已提交到游戏，等待结算后才能锁定；当前未报告锁定成功。'})
                    locks=set(c.planner.config['manual_locks'])
                    if value:locks.add(key)
                    else:locks.discard(key)
                    if not value and key.startswith('equipment:'):
                        c.planner.config['protected_equipment']=[eid for eid in c.planner.config['protected_equipment'] if f'equipment:{eid}'!=key]
                    c.planner.config['manual_locks']=sorted(locks)
                    if value and c.pending and not c.pending_sent and any(keys_overlap(key,used) for used in command_keys(c.pending['kind'],c.pending.get('params',{}),c.state)):
                        c.task_feedback[c.pending['kind']]='固定锁已生效，已取消尚未提交的操作'
                        c.pending=None;c.manual=False
                    atomic_json(RUNTIME/'config.json',c.planner.config)
                    c.log('info',('已固定锁定：' if value else '已解除固定锁：')+key)
                    return self.response(200,{'locked':value,'key':key,'message':'固定锁已保存，所有自动与手动任务均遵守。' if value else '已解除此固定锁，其他保护仍生效。'})
                elif route == '/api/start':
                    if time.monotonic() - c.last_seen >= CONNECTION_TIMEOUT_SECONDS:
                        raise ValueError('尚未连接游戏内桥接')
                    if c.state.get('bridge_revision', 0) < MIN_BRIDGE_REVISION:
                        raise ValueError('等待新版桥接连接；请保持当前游戏运行')
                    if c.state.get('network_blocked'):
                        raise ValueError('请先在游戏中恢复会话')
                    if c.pending:
                        raise ValueError('上一项操作尚未确认，请等待游戏回传结果')
                    c.enabled = True
                    c.resume_requested = True
                    c.started = c.started or time.time()
                    c.log('info', '自动修炼已开始')
                elif route == '/api/stop':
                    c.stop()
                elif route == '/api/connect':
                    if time.monotonic() - c.last_seen < CONNECTION_TIMEOUT_SECONDS:
                        return self.response(200, {'message': '已连接当前游戏，无需重新登录。'})
                    from .install import install
                    installed = install()
                    c.log('info', installed['message'])
                    return self.response(200, installed)
                else:
                    return self.response(404, {'error': 'Not found'})
                return self.response(200, {'ok': True})
        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as error:
            return self.response(400, {'error': str(error)})


def serve(port=17321):
    controller = Controller()
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.controller = controller
    server.daemon_threads = True
    print(f'凡修助手：http://127.0.0.1:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=17321)
    serve(parser.parse_args().port)
