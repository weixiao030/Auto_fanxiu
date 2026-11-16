"""Project resources must use the real response path, independently of the browser."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import urllib.error
import urllib.request
from fanxiu_assistant import server


class ProjectHttpTest(TestCase):
    def test_static_json_script_and_missing_optional_image(self):
        with TemporaryDirectory() as directory, patch.object(server, 'RUNTIME', Path(directory)):
            controller = server.Controller()
            http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            http.controller = controller
            http.daemon_threads = True
            thread = Thread(target=http.serve_forever, daemon=True)
            thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                with opener.open(base + '/project-info.json', timeout=3) as response:
                    self.assertEqual(response.headers.get_content_type(), 'application/json')
                    self.assertEqual(json.load(response), json.loads((server.ROOT / 'web/project-info.json').read_text(encoding='utf-8')))
                with opener.open(base + '/project-info.js', timeout=3) as response:
                    self.assertEqual(response.headers.get_content_type(), 'text/javascript')
                    self.assertEqual(response.read(), (server.ROOT / 'web/project-info.js').read_bytes())
                with opener.open(base + '/api/health', timeout=3) as response:
                    self.assertEqual(json.load(response), {'service': 'fanxiu-local'})
                if not (server.ROOT / 'web/appreciation-code.webp').exists():
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        opener.open(base + '/appreciation-code.webp', timeout=3)
                    self.assertEqual(error.exception.code, 404)
                self.assertFalse(controller.enabled)
                self.assertIsNone(controller.pending)
            finally:
                http.shutdown()
                http.server_close()
                thread.join(3)
