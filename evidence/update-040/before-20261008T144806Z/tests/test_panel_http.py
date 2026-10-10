import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel.server import PanelServer, PanelService
from test_selection import catalog


class PanelHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = PanelService(Path(self.temp.name), catalog)
        self.server = PanelServer(('127.0.0.1', 0), self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        base = {'Content-Type': 'application/json', 'X-Fusion-Token': self.service.token}
        base.update(headers or {})
        connection.request(method, path, json.dumps(body) if body is not None else None, base)
        response = connection.getresponse(); raw = response.read()
        data = json.loads(raw) if response.getheader('Content-Type').startswith('application/json') else raw
        connection.close()
        return response.status, data

    def test_save_reload_and_prepare(self):
        status, state = self.request('GET', '/api/state')
        self.assertEqual(200, status)
        status, saved = self.request('POST', '/api/selection', {'selection': state['default'], 'expected_revision': 'none'})
        self.assertEqual(200, status)
        _, again = self.request('GET', '/api/state')
        self.assertEqual(saved['revision'], again['saved']['revision'])
        status, handoff = self.request('POST', '/api/handoff', {'task': state['task_template'], 'expected_revision': saved['revision']})
        self.assertEqual(200, status)
        self.assertFalse(handoff['manifest']['execution_started'])

    def test_invalid_model_returns_actionable_error(self):
        _, state = self.request('GET', '/api/state')
        value = state['default']; value['worker']['model'] = 'fake'
        status, data = self.request('POST', '/api/selection', {'selection': value, 'expected_revision': 'none'})
        self.assertEqual(400, status); self.assertEqual('invalid_model', data['error']['code'])

    def test_write_error_returns_503(self):
        _, state = self.request('GET', '/api/state')
        with patch.object(self.service.store, 'save', side_effect=OSError('full')):
            status, data = self.request('POST', '/api/selection', {'selection': state['default']})
        self.assertEqual(503, status); self.assertEqual('storage_unavailable', data['error']['code'])

    def test_invalid_body(self):
        status, data = self.request('POST', '/api/selection', [])
        self.assertEqual(400, status)

    def test_foreign_origin_and_bad_token_rejected(self):
        for headers in [{'Origin': 'https://example.com'}, {'X-Fusion-Token': 'wrong'}]:
            status, _ = self.request('POST', '/api/selection', {}, headers)
            self.assertEqual(403, status)

    def test_foreign_host_rejected(self):
        status, _ = self.request('GET', '/api/state', headers={'Host': 'outside.example'})
        self.assertEqual(403, status)

    def test_static_route_does_not_expose_project_files(self):
        status, html = self.request('GET', '/')
        self.assertEqual(200, status); self.assertIn('当前主线程模型'.encode(), html)
        status, _ = self.request('GET', '/../../.codex/config.toml')
        self.assertEqual(404, status)


if __name__ == '__main__': unittest.main()
