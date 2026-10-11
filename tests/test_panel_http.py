# Test storage is deliberately independent of the user's real Codex home.
import os as _test_os, tempfile as _test_tempfile, atexit as _test_atexit
if not _test_os.environ.get('FUSION_TEST_CODEX_HOME'):
    _test_home = _test_tempfile.TemporaryDirectory(prefix='duo-test-home-')
    _test_atexit.register(_test_home.cleanup)
    _test_os.environ['FUSION_TEST_CODEX_HOME'] = _test_home.name
_test_os.environ['CODEX_HOME'] = _test_os.environ['FUSION_TEST_CODEX_HOME']
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
from fusion_selection import saved_workflow


class PanelHTTPTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch as _home_patch
        _home = _test_tempfile.TemporaryDirectory(prefix='duo-case-home-')
        self.addCleanup(_home.cleanup)
        _environment = _home_patch.dict(_test_os.environ, {'CODEX_HOME': _home.name})
        _environment.start(); self.addCleanup(_environment.stop)
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

    def test_global_and_project_scopes_and_reset_use_shared_service(self):
        _, global_state=self.request('GET','/api/state?scope=global')
        workflow={'activation':'automatic_project','coordinator_mode':'current_thread','max_worker_turns':7, 'max_parallel_workers':1}
        status, saved=self.request('POST','/api/selection',{'scope':'global','selection':global_state['default'],
            'workflow':workflow,'expected_revision':'none'})
        self.assertEqual(status,200)
        _, project=self.request('GET','/api/state?scope=project')
        self.assertEqual(project['source'],'global');self.assertIsNone(project['saved']['document'])
        status, local=self.request('POST','/api/selection',{'scope':'project','selection':project['default'],
            'workflow':{**workflow,'activation':'manual'},'expected_revision':'none','expected_global_revision':saved['revision']})
        self.assertEqual(status,200)
        status, restored=self.request('POST','/api/reset',{'project_root':project['project_root'],
            'expected_revision':local['revision'],'expected_global_revision':saved['revision']})
        self.assertEqual(status,200);self.assertEqual(restored['source'],'global')
        self.assertEqual(restored['workflow'],saved_workflow({'workflow': workflow}))

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
        self.assertEqual(200, status); self.assertIn('一个规划，一个执行'.encode(), html); self.assertIn('执行次数上限'.encode(), html)
        status, _ = self.request('GET', '/../../.codex/config.toml')
        self.assertEqual(404, status)


if __name__ == '__main__': unittest.main()
