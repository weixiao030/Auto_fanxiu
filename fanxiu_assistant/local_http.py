"""Direct loopback transport; leaves system, accelerator and Steam proxies intact."""
import json
import threading
import traceback
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
import urllib.request

from .paths import RUNTIME


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def open_local(request, timeout=3):
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password:
        raise ValueError('本机通信仅允许回环地址')
    return _DIRECT.open(request, timeout=timeout)


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def handle_error(self, request, client_address):
        # Windowed executables have no stderr; preserve useful diagnostics on disk.
        RUNTIME.mkdir(parents=True, exist_ok=True)
        with (RUNTIME / 'console-error.log').open('a', encoding='utf-8') as output:
            traceback.print_exc(file=output)


class LocalConsole:
    """Rebind a failed listener without resetting in-flight commands or the game."""
    def __init__(self, controller, handler, port=17321):
        self.controller, self.handler = controller, handler
        self.port = port
        self.http = None
        self.worker = None
        self.closed = threading.Event()
        self.restarts = 0

    def start(self):
        http = ConsoleServer(('127.0.0.1', self.port), self.handler)
        http.controller = self.controller
        self.port = http.server_port
        self.http = http
        self.worker = threading.Thread(target=http.serve_forever, daemon=True)
        self.worker.start()

    def healthy(self):
        try:
            with open_local(f'http://127.0.0.1:{self.port}/api/health', timeout=2) as response:
                return response.status == 200 and json.load(response).get('service') == 'fanxiu-local'
        except (OSError, ValueError):
            return False

    def _close_listener(self):
        if self.http:
            self.http.shutdown()
            self.http.server_close()
            self.http = None
        if self.worker:
            self.worker.join(timeout=2)

    def rebind(self):
        self._close_listener()
        self.start()
        self.restarts += 1
        with self.controller.lock:
            self.controller.log('info', '本机监听已恢复，保留现有任务；代理与游戏连接设置未改变')

    def watch(self):
        failed = 0
        while not self.closed.wait(5):
            if self.healthy():
                failed = 0
                continue
            failed += 1
            if failed < 3:
                continue
            try:
                self.rebind()
                failed = 0
            except OSError as error:
                with self.controller.lock:
                    self.controller.log('warning', f'本机监听恢复失败，将继续重试：{error}')

    def close(self):
        self.closed.set()
        self._close_listener()
