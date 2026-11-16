import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import urllib.request

import fanxiu_assistant.server as server
from fanxiu_assistant.local_http import LocalConsole, open_local


class LocalNetworkTests(unittest.TestCase):
    def test_proxy_is_ignored_only_for_loopback_and_rebind_keeps_pending(self):
        with TemporaryDirectory() as folder, patch.object(server, 'RUNTIME', Path(folder)):
            controller = server.Controller()
            controller.pending = {'id': 'submitted-id', 'kind': 'collect'}
            controller.pending_sent = True
            controller.pending_at = time.monotonic()
            controller.pid = 42
            controller.last_seen = time.monotonic()
            controller.enabled = True
            console = LocalConsole(controller, server.Handler, port=0)
            console.start()
            try:
                # A broken external proxy must not break local UI/bridge communication.
                proxies = {'http_proxy': 'http://127.0.0.1:1', 'HTTP_PROXY': 'http://127.0.0.1:1',
                           'no_proxy': '', 'NO_PROXY': ''}
                with patch.dict(os.environ, proxies):
                    self.assertTrue(console.healthy())
                    url = f'http://127.0.0.1:{console.port}'
                    request = urllib.request.Request(url + '/bridge', data=json.dumps({"pid":42,"state":{"bridge_revision":server.MIN_BRIDGE_REVISION},"busy":True}).encode(),
                                                     headers={'X-Bridge-Key': controller.key})
                    with open_local(request) as response:
                        self.assertEqual(json.load(response)['command']['id'], 'submitted-id')
                    with patch.object(console, 'healthy', return_value=False), patch.object(console.closed, 'wait', side_effect=[False, False, False, True]):
                        console.watch()
                    self.assertTrue(console.healthy())
                    self.assertEqual(os.environ['http_proxy'], proxies['http_proxy'])
                    with open_local(url + '/api/status') as response:
                        status = json.load(response)
                    self.assertEqual(status['pending']['id'], 'submitted-id')
                    self.assertTrue(status['enabled'])
                    self.assertIs(console.http.controller, controller)
                    self.assertEqual(console.restarts, 1)
            finally:
                console.close()

    def test_direct_transport_cannot_be_used_for_external_requests(self):
        for url in ('https://127.0.0.1/', 'http://example.com/', 'http://127.0.0.1.example.com/',
                    'http://user:password@localhost/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                open_local(url)


if __name__ == '__main__':
    unittest.main()
