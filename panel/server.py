#!/usr/bin/env python3
"""Loopback-only panel. Saving/preparing never starts a model task."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/fusion-minimal/skills/fusion/scripts'
sys.path.insert(0, str(SCRIPTS))
from fusion_selection import (SelectionError, SelectionStore, read_catalog, default_selection,
                              presets, prepare_handoff)


from fusion_service import FusionService


class PanelService(FusionService):
    def __init__(self, directory, catalog_loader=read_catalog):
        super().__init__(directory, catalog_loader)
        self.token = secrets.token_urlsafe(32)

    def state(self, scope="project"):
        return {**super().state(scope), 'csrf_token': self.token}


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, service):
        self.service = service
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_data(self, status, data, content_type='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if not isinstance(data, bytes) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        port = self.server.server_port
        return self.headers.get('Host') in [f'127.0.0.1:{port}', f'localhost:{port}']

    def fail(self, error):
        self.send_data(error.status, {'error': {'code': error.code, 'message': str(error)}})

    def do_GET(self):
        if not self.valid_host():
            return self.fail(SelectionError('forbidden', '请求来源不受支持。', 403))
        try:
            route = urlsplit(self.path).path
            if route == '/api/state':
                return self.send_data(200, self.server.service.state(parse_qs(urlsplit(self.path).query).get("scope", ["project"])[0]))
            files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                     '/style.css': ('style.css', 'text/css')}
            if route not in files:
                return self.fail(SelectionError('not_found', '页面不存在。', 404))
            name, content_type = files[route]
            self.send_data(200, (ROOT / 'panel/static' / name).read_bytes(), content_type + '; charset=utf-8')
        except SelectionError as exc:
            self.fail(exc)
        except OSError:
            self.fail(SelectionError('storage_unavailable', '无法读取本地文件，请检查目录权限。', 503))

    def do_POST(self):
        origin = self.headers.get('Origin')
        port = self.server.server_port
        if not self.valid_host() or (origin and origin not in [f'http://127.0.0.1:{port}', f'http://localhost:{port}']) or not secrets.compare_digest(self.headers.get('X-Fusion-Token', ''), self.server.service.token):
            return self.fail(SelectionError('forbidden', '请求已过期或来源不受支持，请刷新面板。', 403))
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.headers.get_content_type() != 'application/json' or not 0 < length <= 65536:
                raise SelectionError('invalid_request', '请求必须是有效的 JSON，大小不超过 64 KiB。')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('object required')
            route = urlsplit(self.path).path
            if route == '/api/selection':
                return self.send_data(200, self.server.service.save(body))
            if route == '/api/reset':
                return self.send_data(200, self.server.service.reset(body))
            if route == '/api/handoff':
                return self.send_data(200, self.server.service.prepare(body))
            raise SelectionError('not_found', '接口不存在。', 404)
        except SelectionError as exc:
            self.fail(exc)
        except (ValueError, TypeError):
            self.fail(SelectionError('invalid_request', '请求格式无效。'))
        except OSError:
            self.fail(SelectionError('storage_unavailable', '保存失败，请检查目录权限和磁盘空间。', 503))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state-dir', type=Path, default=ROOT / '.fusion')
    args = parser.parse_args()
    server = PanelServer(('127.0.0.1', args.port), PanelService(args.state_dir))
    print(f'Fusion panel: http://127.0.0.1:{server.server_port}', flush=True)
    print(f'Local state: {args.state_dir} | Saving does not start tasks.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
