"""Run the additive v0.3 PoC without changing the existing app."""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from . import reader, poc_analysis
from .notes import load_notes


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--base', default='HEAD~1')
    p.add_argument('--head', default='HEAD')
    p.add_argument('--port', type=int, default=8766)
    p.add_argument('--notes', type=Path)
    a = p.parse_args()
    snapshot = reader.snapshot(a.repo, a.base, a.head, with_graphs=False)
    snapshot['notes'] = load_notes(a.notes, snapshot['meta'])
    result = None
    lock = threading.Lock()
    static = Path(__file__).with_name('poc_static')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal result
            url = urlparse(self.path); q = parse_qs(url.query)
            try:
                if url.path == '/api/snapshot':
                    payload = reader.public(snapshot)
                elif url.path == '/api/file':
                    payload = reader.file_diff(snapshot, q.get('file', [''])[0])
                elif url.path == '/api/analysis':
                    with lock:
                        if result is None:
                            result = poc_analysis.analyze(snapshot)
                        payload = result
                else:
                    routes = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/cytoscape.min.js': ('cytoscape.min.js', 'text/javascript')}
                    if url.path not in routes:
                        self.respond(404, b'Not found', 'text/plain'); return
                    name, kind = routes[url.path]
                    self.respond(200, (static / name).read_bytes(), kind); return
                self.respond(200, json.dumps(payload, ensure_ascii=True).encode(), 'application/json')
            except (ValueError, OSError, RecursionError) as exc:
                self.respond(400, json.dumps({'error': str(exc)}, ensure_ascii=True).encode(), 'application/json')

        def respond(self, status, body, kind):
            self.send_response(status)
            self.send_header('Content-Type', kind+'; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers(); self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'PLISM v0.3 PoC http://127.0.0.1:{a.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
