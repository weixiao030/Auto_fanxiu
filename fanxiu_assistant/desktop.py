from pathlib import Path
import ctypes
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from . import server
from .game_location import detect_game, remember_game
from .install import install, game_processes
from .paths import DATA, ROOT, RUNTIME, prepare_resources
from .supervisor import Supervisor, launch_steam
from .windows import listener_process, end_helper_process
from .version import APP_TITLE, APP_NAME, VERSION
from .local_http import open_local, LocalConsole

URL = 'http://127.0.0.1:17321'


def existing_service():
    try:
        with open_local(URL+'/api/status', timeout=2) as response:
            value = json.load(response)
        return value if value.get('labels', {}).get('gacha') == '悟性化物' and isinstance(value.get('config'), dict) else None
    except (OSError, ValueError):
        return False


def version_tuple(value):
    parts=str(value).split('.')
    return tuple(map(int,parts)) if len(parts)==2 and all(p.isascii() and p.isdigit() for p in parts) else ()


def replace_older_helper(current):
    """Upgrade only our verified older listener after every submitted operation settles."""
    old=version_tuple(current.get('app_version'));new=version_tuple(VERSION)
    if not old or not new or old>=new:return False
    pid,image=listener_process(17321)
    if image.name!=f"{APP_NAME}{current['app_version']}.exe":
        raise RuntimeError('本机端口由其他程序占用，未结束任何进程')
    request=urllib.request.Request(URL+'/api/stop',data=b'{}',headers={'Origin':URL,'X-CSRF-Token':current['csrf'],'Content-Type':'application/json'})
    with open_local(request,timeout=5) as response:json.load(response)
    deadline=time.monotonic()+335
    while True:
        current=existing_service()
        if not current:raise RuntimeError('旧助手状态不可读，未强制接替')
        if not current.get('pending') and not current.get('state',{}).get('battle') and not current.get('state',{}).get('battle_pending') and not current.get('state',{}).get('pending'):break
        if time.monotonic()>=deadline:raise RuntimeError('等待旧助手当前操作结算；未关闭游戏或Steam')
        time.sleep(1)
    end_helper_process(pid,image)
    # The frozen parent releases its mutex after the listener child exits.
    for _ in range(40):
        if not existing_service():break
        time.sleep(.25)
    return True


def notify(message, error=False):
    ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10 if error else 0x40)


def choose_game():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    try:
        value = filedialog.askdirectory(title='请选择Steam凡修安装目录（包含run.exe）', parent=root)
        return remember_game(value) if value else None
    finally:
        root.destroy()


def main():
    current=existing_service()
    if current:
        try:
            replaced=replace_older_helper(current)
        except (OSError,ValueError,RuntimeError,KeyError) as error:
            notify(str(error),True)
            return
        if not replaced:
            webbrowser.open(URL)
            return
    prepare_resources()
    # The mutex closes the launch race without depending on Python or a shell.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    name = 'Local\\FanxiuAssistant-' + hashlib.sha256(str(DATA).encode()).hexdigest()[:16]
    mutex = kernel.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == 183:
        for _ in range(40):
            if existing_service():
                kernel.CloseHandle(ctypes.c_void_p(mutex))
                webbrowser.open(URL)
                return
            kernel.CloseHandle(ctypes.c_void_p(mutex))
            time.sleep(.25)
            mutex=kernel.CreateMutexW(None,False,name)
            if ctypes.get_last_error()!=183:break
        else:
            kernel.CloseHandle(ctypes.c_void_p(mutex))
            notify('助手正在接替旧版，请稍候或检查本机17321端口。')
            return
    try:
        game = detect_game() or choose_game()
        if not game:
            return
        remember_game(game)
        install()
        from .session_upgrade import stage_bridge
        stage_bridge(ROOT / 'bridge')
        controller = server.Controller()
        # A normal double-click resumes the latest automation once its bridge is ready.
        controller.resume_requested = True
        console = LocalConsole(controller, server.Handler)
        console.start()
        threading.Thread(target=console.watch, daemon=True).start()
        supervisor = Supervisor(controller, game)
        threading.Thread(target=supervisor.run, daemon=True).start()
        if not game_processes(game) and controller.planner.config.get('allow_game_restart', False):
            launch_steam()
        webbrowser.open(URL)
        while not console.closed.is_set():
            time.sleep(1)
    except Exception as error:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        (RUNTIME/'startup-error.log').write_text(type(error).__name__+': '+str(error), encoding='utf-8')
        notify(str(error)+'\n\n可查看用户目录中的 runtime/startup-error.log。', True)
    finally:
        if mutex:
            kernel.CloseHandle(ctypes.c_void_p(mutex))


def self_test(report):
    prepare_resources()
    controller = server.Controller()
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    http.controller, http.daemon_threads = controller, True
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{http.server_port}'
    try:
        with open_local(base+'/api/status') as response:
            status = json.load(response)
        with open_local(base) as response:
            html = response.read().decode('utf-8')
        for resource in ('app.js','inventory.js','style.css'):
            with open_local(base+'/'+resource) as response:
                assert response.status==200 and response.read()==(ROOT/'web'/resource).read_bytes()
        config = status['config']
        from .settings import DEFAULTS, validate_config
        assert config == validate_config({}) == DEFAULTS
        assert '凡修自动化工作台' in html
        assert (ROOT/'bridge/assistant.gd').is_file() and (ROOT/'bridge/loader.gd').is_file() and (ROOT/'bridge/inventory.gd').is_file() and (ROOT/'bridge/steam_inventory.gd').is_file()
        result = {'status': 'PASS', 'frozen': bool(getattr(sys, 'frozen', False)),
                  'python': sys.version.split()[0], 'defaults': {k:config[k] for k in ('preserve_steam_tradable','preserve_tradable','min_breakthrough_rate','reserve_wuxing','auto_reconnect','auto_steam_update')},
                  'config': config, 'defaults_match_packaged_strategy': True,
                  'http': True, 'bundled_web_and_bridge': True, 'real_game_mutations': 0}
        Path(report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        http.shutdown()
        http.server_close()
