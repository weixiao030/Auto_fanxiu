"""Recover a local client and ask the official Steam client to update before launch."""
from pathlib import Path
import json
import os
import re
import threading
import time
import urllib.request
from .game_location import APP_ID
from .install import game_processes
from .windows import close_window
from .connection import HEARTBEAT_FRESH_SECONDS, CONNECTION_TIMEOUT_SECONDS
from .server import MIN_BRIDGE_REVISION
from .readiness import waiting_message


def steam_update_needed(game):
    manifest = Path(game).parent.parent / f'appmanifest_{APP_ID}.acf'
    if not manifest.is_file():
        return False
    text = manifest.read_text(encoding='utf-8-sig')
    match = re.search(r'"buildid"\s*"(\d+)"', text)
    if not match:
        return False
    request = urllib.request.Request(
        f'https://api.steampowered.com/ISteamApps/UpToDateCheck/v1/?appid={APP_ID}&version={match[1]}',
        headers={'User-Agent': 'FanxiuLocalAssistant/1.0'})
    with urllib.request.urlopen(request, timeout=8) as response:
        result = json.load(response).get('response', {})
    if not result.get('success') or type(result.get('up_to_date')) is not bool:
        raise ValueError('Steam未返回有效更新状态')
    return not result['up_to_date']


def launch_steam():
    # Steam performs its normal update/download checks before launching the game.
    os.startfile(f'steam://rungameid/{APP_ID}')


def steam_install_state(game):
    manifest = Path(game).parent.parent / f'appmanifest_{APP_ID}.acf'
    try:
        text = manifest.read_text(encoding='utf-8-sig')
        match = re.search(r'"StateFlags"\s*"(\d+)"', text)
        flags = int(match[1]) if match else 0
        return {'update_required': bool(flags & 2), 'downloading': bool(flags & (256 | 512 | 1024)),
                'fully_installed': bool(flags & 4)}
    except OSError:
        return {}


class Supervisor:
    def __init__(self, controller, game):
        self.controller, self.game = controller, Path(game)
        self.lost_at = None
        self.next_retry = 0
        self.attempts = 0
        self.next_update = 0
        self.update_pending = False
        self.restarted_pid = None
        self.closed = threading.Event()

    def status(self, message):
        with self.controller.lock:
            self.controller.maintenance = {'message': message, 'attempts': self.attempts,
                'update_pending': self.update_pending, 'next_retry_seconds': max(0, round(self.next_retry-time.monotonic()))}

    def restart(self):
        # Final guard also covers direct calls and settings changed after step().
        with self.controller.lock:
            if not self.controller.planner.config.get('allow_game_restart', False):
                raise RuntimeError('禁止重启游戏已生效；保留当前会话或队列')
        pids = game_processes(self.game)
        if len(pids) > 1:
            raise RuntimeError('检测到多个游戏实例，等待用户处理')
        if pids:
            if not close_window(pids[0]):
                raise RuntimeError('游戏没有可正常关闭的窗口，未强制结束进程')
            deadline = time.monotonic() + 20
            while game_processes(self.game):
                if self.closed.wait(.5) or time.monotonic() >= deadline:
                    raise RuntimeError('等待游戏正常退出，未启动第二实例')
        self.restarted_pid = pids[0] if pids else getattr(self.controller, "pid", None)
        launch_steam()

    def step(self, now=None):
        now = time.monotonic() if now is None else now
        c = self.controller
        with c.lock:
            config, state = dict(c.planner.config), dict(c.state)
            connected = now - c.last_seen < CONNECTION_TIMEOUT_SECONDS and (self.restarted_pid is None or c.pid != self.restarted_pid)
            pending = bool(c.pending)
            wanted = c.resume_requested
        if connected:
            if now-c.last_seen >= HEARTBEAT_FRESH_SECONDS:
                self.status('游戏心跳稍有延迟，保持会话并等待新状态；不重启游戏')
                return
            if self.restarted_pid is not None:
                self.update_pending = False
            self.restarted_pid = None
            self.lost_at = None
            if not state.get('ready'):
                self.status(waiting_message(state))
                return
            if state.get('network_blocked'):
                self.status('游戏正在恢复会话；由原客户端自动重连，登录冲突等待用户处理')
                return
            if state.get('ready') and state.get('bridge_revision',0)<MIN_BRIDGE_REVISION and wanted:
                if pending or state.get('battle') or state.get('battle_pending') or state.get('pending',0):
                    self.status('等待当前操作结算后加载新版桥接')
                    return
                if not config.get('allow_game_restart', False):
                    self.status('等待自有桥接在空闲边界更新；保留当前游戏和排队会话')
                    return
                self.status('正在正常重开当前凡修以加载新版桥接；不重启Steam')
                self.restart()
                self.lost_at=now
                self.next_retry=now+180
                return
            if state.get('ready') and state.get('bridge_revision', 0) >= MIN_BRIDGE_REVISION:
                if config['auto_reconnect'] and wanted and not pending:
                    with c.lock:
                        if not c.enabled:
                            c.enabled = True
                            c.log('info', '游戏会话已恢复，继续自动修炼')
                self.attempts = 0
                self.next_retry = 0
            if not config.get('allow_game_restart', False):
                self.status('连接正常；禁止重启游戏，更新延后至允许重启时')
                return
            client_update=state.get('client_update', {}).get('state') in ('required','available')
            if config['auto_steam_update'] and client_update:
                self.update_pending=True
            if config['auto_steam_update'] and not self.update_pending and now >= self.next_update:
                self.next_update = now + config['steam_update_interval']
                try:
                    self.update_pending = steam_update_needed(self.game)
                except (OSError, ValueError, TimeoutError):
                    self.status('Steam更新检查暂不可用，将按配置间隔重试')
                    return
            if self.update_pending:
                if pending or state.get('battle') or state.get('pending', 0):
                    self.status('Steam有更新，等待当前战斗和操作结束')
                    return
                self.status('正在正常关闭游戏，通过Steam更新后重开')
                self.restart()
                # Keep update intent visible until a fresh client heartbeat arrives.
                self.lost_at = now
                self.next_retry = now + 180  # Steam may need time to download.
                return
            self.status('连接正常；Steam按计划检查更新')
            return
        if not config.get('allow_game_restart', False):
            self.status('等待当前原生客户端恢复连接；禁止重启或启动第二实例')
            return
        if not config['auto_reconnect']:
            self.status('自动恢复已关闭')
            return
        installation=steam_install_state(self.game)
        if installation.get('update_required'):
            self.update_pending=True
        self.lost_at = self.lost_at if self.lost_at is not None else now
        delay = config['reconnect_delay_seconds']
        if now-self.lost_at < delay or now < self.next_retry:
            self.status('等待Steam下载更新；下载失败时由Steam重试，助手不启动旧版' if self.update_pending else '连接中断，等待恢复间隔')
            return
        limit = config['reconnect_max_attempts']
        if limit and self.attempts >= limit:
            self.status('已到恢复次数上限，请检查Steam或提高重试上限')
            return
        self.attempts += 1
        self.next_retry = now + (600 if self.update_pending else min(600, delay * 2 ** min(self.attempts-1, 5)))
        self.status('正在通过Steam恢复游戏连接')
        self.restart()

    def run(self):
        while not self.closed.is_set():
            try:
                self.step()
            except (OSError, ValueError, RuntimeError, TimeoutError) as error:
                self.status(str(error))
            self.closed.wait(2)
