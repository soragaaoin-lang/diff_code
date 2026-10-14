import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .analyzer import analyze, graph_at_depth
from .report import markdown_report
from . import reader
from .notes import load_notes


def main():
    parser = argparse.ArgumentParser(description='Local Python Codegraph')
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--base', default='HEAD')
    parser.add_argument('--head', default='WORKTREE')
    parser.add_argument('--depth', type=int, choices=[1, 2], default=2)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--condition', choices=['A', 'B', 'C'], default='C', help='Reviewer study condition (fixed for this server)')
    parser.add_argument('--notes', type=Path, help='Human-authored reading notes JSON for one comparison')
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--export', type=Path, help='Write graph JSON and exit')
    parser.add_argument('--report', type=Path, help='Write Markdown review report and exit')
    args = parser.parse_args()
    try:
        initial = analyze(args.repo, args.base, args.head, args.depth)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.export:
        args.export.write_text(json.dumps(initial, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.report:
        args.report.write_text(markdown_report(initial), encoding='utf-8')
    if args.export or args.report:
        return
    static = Path(__file__).parent / 'static'
    lock = threading.Lock()
    cache = {(args.base, args.head): initial}
    reviews = {}

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, body, content_type):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ('/api/review', '/api/file', '/api/relations'):
                query = parse_qs(url.query)
                try:
                    if url.path == '/api/review':
                        base = query.get('base', [args.base])[0]
                        head = query.get('head', ['HEAD' if args.head == 'WORKTREE' else args.head])[0]
                        result = reader.snapshot(args.repo, base, head, with_graphs=False)
                        result['meta']['condition'] = args.condition
                        result['notes'] = load_notes(args.notes, result['meta'])
                        with lock:
                            reviews[result['meta']['snapshot_id']] = result
                            while len(reviews) > 4:
                                del reviews[next(iter(reviews))]
                        payload = reader.public(result)
                    else:
                        with lock:
                            result = reviews.get(query.get('snapshot', [''])[0])
                        if result is None:
                            raise ValueError('比較データがありません。比較を開き直してください。')
                        if url.path == '/api/relations':
                            if args.condition == 'A':
                                raise ValueError('この評価条件では関係解析を表示しません。')
                            if result['graphs'] is None:
                                # Keep slow analysis outside the cache lock so text stays available.
                                result['graphs'] = reader.graph_data(args.repo, result['meta']['base_commit'], result['meta']['head_commit'])
                            payload = result['graphs']
                        else:
                            payload = reader.file_diff(result, query.get('file', [''])[0])
                    self.respond(200, json.dumps(payload, ensure_ascii=True).encode(), 'application/json; charset=utf-8')
                except (ValueError, OSError) as exc:
                    self.respond(400, json.dumps({'error': str(exc)}).encode(), 'application/json')
                return
            if url.path == '/api/graph':
                query = parse_qs(url.query)
                try:
                    base = query.get('base', [args.base])[0]
                    head = query.get('head', [args.head])[0]
                    depth = int(query.get('depth', [str(args.depth)])[0])
                    if depth not in (1, 2):
                        raise ValueError('depth must be 1 or 2')
                    key = (base, head)
                    with lock:
                        if query.get('refresh') or key not in cache:
                            result = analyze(args.repo, base, head, depth)
                            cache.clear()
                            cache[key] = result
                        graph = graph_at_depth(cache[key], depth)
                    self.respond(200, json.dumps(graph, ensure_ascii=False).encode(), 'application/json; charset=utf-8')
                except (ValueError, OSError) as exc:
                    self.respond(400, json.dumps({'error': str(exc)}).encode(), 'application/json')
                return
            routes = {'/': 'index.html', '/app.js': 'reader-ui.js', '/style.css': 'style.css',
                      '/vendor/cytoscape.min.js': 'vendor/cytoscape.min.js', '/reading-notes.js': 'reading-notes.js'}
            if url.path not in routes:
                self.respond(404, b'Not found', 'text/plain')
                return
            path = static / routes[url.path]
            types = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}
            self.respond(200, path.read_bytes(), types[path.suffix])

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Codegraph: http://127.0.0.1:{args.port}  (Ctrl+C to stop)', flush=True)
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
