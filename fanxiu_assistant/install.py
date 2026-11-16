from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess

from .paths import ROOT, RUNTIME, BACKUPS
from .game_location import detect_game
from .windows import process_images

MARK_BEGIN = '; FANXIU_ASSISTANT_BEGIN'
MARK_END = '; FANXIU_ASSISTANT_END'


def game_folder():
    folder = detect_game()
    if folder is None:
        raise RuntimeError('未找到凡修安装目录，请重新打开助手并选择游戏目录')
    return folder


def game_processes(folder=None):
    target = str((folder or game_folder()) / 'run.exe').casefold()
    return [pid for pid, image in process_images() if str(image).casefold() == target]


def install():
    GAME = game_folder()
    import secrets
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not (RUNTIME / 'bridge.key').exists():
        previous = (GAME / 'fanxiu-assistant.key').read_text(encoding='utf-8').strip() if (GAME / 'fanxiu-assistant.key').is_file() else ''
        key = previous if len(previous) == 64 and all(c in '0123456789abcdef' for c in previous) else secrets.token_hex(32)
        (RUNTIME / 'bridge.key').write_text(key, encoding='utf-8')
    if not (GAME / 'run.exe').exists():
        raise RuntimeError('未找到凡修安装目录')
    # Version metadata is informational, never an installation allowlist.
    try:
        manifest = json.loads((GAME / 'release-manifest.json').read_text(encoding='utf-8-sig'))
        version = manifest.get('version', 'unknown') if isinstance(manifest, dict) else 'unknown'
    except (OSError, ValueError):
        version = 'unknown'
    settings = GAME / 'override.cfg'
    current = settings.read_text(encoding='utf-8-sig') if settings.exists() else ''
    bridge_path = (ROOT / 'bridge/loader.gd').as_posix()
    block = f'{MARK_BEGIN}\n[autoload]\nFanxiuAssistant="*{bridge_path}"\n{MARK_END}'
    if (MARK_BEGIN in current) != (MARK_END in current):
        raise RuntimeError('助手设置标记不完整，请先检查 override.cfg')
    if MARK_BEGIN in current:
        before, rest = current.split(MARK_BEGIN, 1)
        _, after = rest.split(MARK_END, 1)
        updated = before + block + after
    else:
        updated = current.rstrip() + '\n' + block + '\n'
    if updated != current:
        backup = BACKUPS / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True)
        if settings.exists():
            shutil.copy2(settings, backup / 'override.cfg')
        (backup / 'manifest.json').write_text(json.dumps({'override_existed': settings.exists(), 'game_version': version}, ensure_ascii=False), encoding='utf-8')
        (RUNTIME / 'install.json').write_text(json.dumps({'backup': str(backup), 'game': str(GAME)}, ensure_ascii=False), encoding='utf-8')
        temp = GAME / 'override.cfg.assistant.tmp'
        temp.write_text(updated, encoding='utf-8')
        temp.replace(settings)
    key_target = GAME / 'fanxiu-assistant.key'
    if not key_target.exists() or key_target.read_bytes() != (RUNTIME / 'bridge.key').read_bytes():
        if key_target.exists():
            backup = BACKUPS / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            backup.mkdir(parents=True)
            shutil.copy2(key_target, backup / key_target.name)
        temporary = key_target.with_suffix('.key.tmp')
        shutil.copy2(RUNTIME / 'bridge.key', temporary)
        temporary.replace(key_target)
    return {'installed': True, 'running_pids': game_processes(),
            'message': '桥接已就绪。关闭当前游戏后，从 Steam 正常打开一次即可连接；网页无需登录。'}


def uninstall():
    GAME = game_folder()
    settings = GAME / 'override.cfg'
    if settings.exists():
        current = settings.read_text(encoding='utf-8-sig')
        if MARK_BEGIN in current and MARK_END in current:
            before, rest = current.split(MARK_BEGIN, 1)
            _, after = rest.split(MARK_END, 1)
            updated = before.rstrip() + after
            backup = BACKUPS / ('uninstall-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            backup.mkdir(parents=True)
            shutil.copy2(settings, backup / 'override.cfg')
            temp = GAME / 'override.cfg.assistant.tmp'
            temp.write_text(updated, encoding='utf-8')
            temp.replace(settings)
    print('已移除助手自动加载设置，重启游戏后生效。备份保留在用户数据目录。')


def launch():
    GAME = game_folder()
    pids = game_processes()
    if pids:
        print(f'检测到游戏已运行（PID {pids}），仅连接控制台，不启动第二实例。')
        return False
    install()
    subprocess.Popen([str(GAME / 'run.exe')], cwd=GAME,
                     creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'uninstall', 'launch', 'status'], default='status', nargs='?')
    action = parser.parse_args().action
    if action == 'install': print(json.dumps(install(), ensure_ascii=False, indent=2))
    elif action == 'uninstall': uninstall()
    elif action == 'launch': launch()
    else: print(game_processes())
