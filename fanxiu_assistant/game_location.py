from pathlib import Path
import json
import os
import re
from .paths import RUNTIME
from .windows import process_images

APP_ID = '3301840'


def is_game(path):
    path = Path(path)
    if not (path / 'run.exe').is_file():
        return False
    try:
        manifest = json.loads((path / 'release-manifest.json').read_text(encoding='utf-8-sig'))
        if isinstance(manifest, dict) and 'app_id' in manifest:
            return str(manifest['app_id']) == APP_ID
    except (OSError, ValueError):
        pass
    # A damaged release manifest is acceptable only when Steam confirms identity.
    path = path.resolve()
    steamapps = path.parent.parent
    try:
        text = (steamapps / f'appmanifest_{APP_ID}.acf').read_text(encoding='utf-8-sig')
        app = re.search(r'"appid"\s*"([^"\n]+)"', text)
        folder = re.search(r'"installdir"\s*"([^"\n]+)"', text)
        common = (steamapps / 'common').resolve()
        target = (common / folder[1]).resolve() if folder else None
        return bool(app and app[1] == APP_ID and target == path and target.is_relative_to(common))
    except (OSError, ValueError):
        return False


def steam_roots():
    roots = []
    if os.name == 'nt':
        import winreg
        for hive, key, field in [(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                 (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')]:
            try:
                with winreg.OpenKey(hive, key) as handle:
                    roots.append(Path(winreg.QueryValueEx(handle, field)[0]))
            except OSError:
                pass
    roots.append(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Steam')
    return list(dict.fromkeys(roots))


def steam_libraries(roots=None):
    libraries = list(steam_roots() if roots is None else roots)
    for root in list(libraries):
        vdf = root / 'steamapps/libraryfolders.vdf'
        if vdf.is_file():
            for value in re.findall(r'"path"\s*"([^"]+)"', vdf.read_text(encoding='utf-8-sig')):
                libraries.append(Path(value.replace('\\\\', '\\')))
    return list(dict.fromkeys(libraries))


def detect_game():
    for _, image in process_images():
        if is_game(image.parent):
            return image.parent
    saved = RUNTIME / 'game-location.json'
    if saved.is_file():
        try:
            value = Path(json.loads(saved.read_text(encoding='utf-8'))['path'])
            if is_game(value):
                return value
        except (OSError, ValueError, KeyError, TypeError):
            pass
    for library in steam_libraries():
        manifest = library / f'steamapps/appmanifest_{APP_ID}.acf'
        if manifest.is_file():
            match = re.search(r'"installdir"\s*"([^"]+)"', manifest.read_text(encoding='utf-8-sig'))
            common = (library / 'steamapps/common').resolve()
            folder = (common / match[1]).resolve() if match else common / 'fanxiu'
            if folder.is_relative_to(common) and is_game(folder):
                return folder
    return None


def remember_game(folder):
    folder = Path(folder).resolve()
    if not is_game(folder):
        raise ValueError('请选择经凡修 App ID 或 Steam 安装清单确认的游戏目录（包含 run.exe）')
    RUNTIME.mkdir(parents=True, exist_ok=True)
    temp = RUNTIME / 'game-location.json.tmp'
    temp.write_text(json.dumps({'path': str(folder)}, ensure_ascii=False), encoding='utf-8')
    temp.replace(RUNTIME / 'game-location.json')
    return folder
