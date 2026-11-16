"""Start the local console only. Never signs in or spawns a duplicate game."""
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser
from fanxiu_assistant.local_http import open_local

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:17321'


def alive():
    try:
        with open_local(URL + '/api/status', timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


if __name__ == '__main__':
    if not alive():
        logs = ROOT / 'runtime'
        logs.mkdir(exist_ok=True)
        with (logs / 'server.log').open('ab') as output:
            subprocess.Popen([sys.executable, '-m', 'fanxiu_assistant.server'], cwd=ROOT,
                             stdout=output, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for _ in range(30):
            if alive(): break
            time.sleep(0.2)
        else:
            raise SystemExit('启动失败，请查看 runtime/server.log')
    webbrowser.open(URL)
    print('本地控制台已打开；不会启动第二个游戏或进行登录。')
