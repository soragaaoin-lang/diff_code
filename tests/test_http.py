import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

from test_review import ReviewTests as _RepositoryFixture


class HTTPTests(_RepositoryFixture):
    def start_server(self, *extra):
        import socket
        with socket.socket() as socket_probe:
            socket_probe.bind(('127.0.0.1', 0))
            port = socket_probe.getsockname()[1]
        process = subprocess.Popen([sys.executable, '-m', 'codegraph', '--repo', str(self.repo), '--port', str(port), *extra],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_server, process)
        self.url = f'http://127.0.0.1:{port}'
        for _ in range(100):
            if process.poll() is not None:
                self.fail('HTTP server exited during startup')
            try:
                return self.fetch('/api/graph')
            except urllib.error.URLError:
                time.sleep(.05)
        self.fail('HTTP server did not start')

    @staticmethod
    def stop_server(process):
        process.terminate()
        process.wait(timeout=10)

    def fetch(self, route):
        with urllib.request.urlopen(self.url + route, timeout=10) as response:
            return json.loads(response.read())

    def test_depth_uses_snapshot_until_refresh(self):
        self.write('p.py', 'def a():\n    return 1\ndef b():\n    return a()\ndef c():\n    return b()\n')
        self.commit()
        self.write('p.py', 'def a():\n    return 2\ndef b():\n    return a()\ndef c():\n    return b()\n')
        first = self.start_server()
        self.write('p.py', 'def unrelated():\n    pass\n')
        shallow = self.fetch('/api/graph?depth=1')
        self.assertEqual(first['meta']['snapshot_id'], shallow['meta']['snapshot_id'])
        self.assertEqual(shallow['meta']['affected'], 1)
        refreshed = self.fetch('/api/graph?depth=1&refresh=1')
        self.assertNotEqual(first['meta']['snapshot_id'], refreshed['meta']['snapshot_id'])

    def test_errors_leave_previous_snapshot_and_static_routes(self):
        self.write('p.py', 'def a():\n    pass\n')
        self.commit()
        first = self.start_server()
        for route in ['/api/graph?depth=3', '/api/graph?base=missing&refresh=1']:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.fetch(route)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        self.assertEqual(first['meta']['snapshot_id'], self.fetch('/api/graph')['meta']['snapshot_id'])
        for route in ['/', '/app.js', '/style.css', '/vendor/cytoscape.min.js']:
            with urllib.request.urlopen(self.url + route, timeout=10) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.fetch('/../analyzer.py')
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_cli_markdown_and_json_export(self):
        self.write('p.py', 'def a():\n    return 1\n')
        self.commit()
        self.write('p.py', 'def a():\n    return 2\n')
        report, graph = self.repo / 'review.md', self.repo / 'graph.json'
        subprocess.run([sys.executable, '-m', 'codegraph', '--repo', str(self.repo), '--report', str(report), '--export', str(graph)],
                       check=True, capture_output=True)
        self.assertIn('PLISM Change Review', report.read_text(encoding='utf-8'))
        self.assertEqual(json.loads(graph.read_text(encoding='utf-8'))['meta']['changed'], 1)

    def test_review_condition_and_lazy_relations(self):
        self.write('p.py', 'def a():\n    return 1\n')
        self.commit()
        self.write('p.py', 'def a():\n    return 2\n')
        self.commit()
        self.start_server('--base', 'HEAD~1', '--head', 'HEAD', '--condition', 'B')
        review = self.fetch('/api/review')
        self.assertEqual(review['meta']['condition'], 'B')
        self.assertIsNone(review['graphs'])
        self.assertNotIn('_trees', review)
        key = review['meta']['snapshot_id']
        data = self.fetch('/api/file?snapshot=' + key + '&file=p.py')
        self.assertEqual(data['head']['lines'][1], '    return 2')
        self.assertIn('head', self.fetch('/api/relations?snapshot=' + key))
        self.start_server('--base', 'HEAD~1', '--head', 'HEAD', '--condition', 'A')
        review = self.fetch('/api/review')
        self.assertEqual(review['meta']['condition'], 'A')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.fetch('/api/relations?snapshot=' + review['meta']['snapshot_id'])
        self.assertEqual(error.exception.code, 400)
        error.exception.close()


# Reuse only repository setup methods, not the inherited analyzer/review cases.
for _name in _RepositoryFixture.__dict__:
    if _name.startswith('test_'):
        setattr(HTTPTests, _name, None)
del _RepositoryFixture
