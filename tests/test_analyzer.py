import subprocess
import tempfile
import unittest
from pathlib import Path

from codegraph.analyzer import analyze, index


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name).resolve()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Codegraph test')
        self.git('config', 'user.email', 'test@example.invalid')

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)

    def write(self, path, source):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding='utf-8')

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')

    def test_worktree_hops_and_evidence(self):
        before = 'def normalize(x):\n    return x\n\ndef build(x):\n    return normalize(x)\n\ndef export(x):\n    return build(x)\n'
        self.write('pipeline.py', before)
        self.commit()
        self.write('pipeline.py', before.replace('return x', 'return x.strip()'))
        one = analyze(self.repo, depth=1)
        two = analyze(self.repo, depth=2)
        self.assertEqual([n['name'] for n in one['nodes'] if n['changed']], ['normalize'])
        self.assertEqual({n['name'] for n in one['nodes'] if n['affected']}, {'build'})
        self.assertEqual({n['name'] for n in two['nodes'] if n['affected']}, {'build', 'export'})
        self.assertEqual({e['line'] for e in two['edges'] if e['impact']}, {5, 8})

    def test_deleted_definition_preserves_base_calls(self):
        self.write('p.py', 'def gone():\n    return 1\n\ndef caller():\n    return gone()\n')
        self.commit()
        self.write('p.py', 'def caller():\n    return gone()\n')
        graph = analyze(self.repo)
        self.assertTrue(next(n for n in graph['nodes'] if n['name'] == 'gone')['deleted'])
        self.assertTrue(next(n for n in graph['nodes'] if n['name'] == 'caller')['affected'])
        self.assertTrue(any(e['deleted'] and e['impact'] for e in graph['edges']))

    def test_committed_head_is_not_worktree(self):
        self.write('p.py', 'def f():\n    return 1\n')
        self.commit()
        self.write('p.py', 'def f():\n    return 2\n')
        self.commit()
        self.write('p.py', 'def unrelated():\n    pass\n')
        graph = analyze(self.repo, base='HEAD~1', head='HEAD')
        self.assertIn('f', [n['name'] for n in graph['nodes']])
        self.assertNotIn('unrelated', [n['name'] for n in graph['nodes']])

    def test_imports_methods_nested_and_ambiguity(self):
        nodes, edges, warnings, _ = index({
            'src/pkg/a.py': 'def clean(x):\n    return x\n',
            'src/pkg/b.py': 'from .a import clean as tidy\nclass Store:\n    def save(self, x):\n        return tidy(x)\n    def preview(self, x):\n        return self.save(x)\ndef outer():\n    def inner():\n        return 1\n    return inner()\n',
            'other.py': 'def clean(x):\n    return x\ndef unknown(obj):\n    return obj.clean(1)\n'})
        pairs = {(nodes[e['source']]['qualname'], nodes[e['target']]['qualname']) for e in edges}
        self.assertIn(('Store.save', 'clean'), pairs)
        self.assertIn(('Store.preview', 'Store.save'), pairs)
        self.assertIn(('outer', 'outer.inner'), pairs)
        self.assertFalse(any(a == 'unknown' for a, b in pairs))
        self.assertFalse(warnings)

    def test_untracked_unicode_and_syntax_warning(self):
        self.write('初期.py', 'def f():\n    return 1\n')
        self.commit()
        self.write('初期.py', 'def f():\n    return 2\n')
        self.write('new.py', 'def fresh():\n    pass\n')
        self.write('broken.py', 'def (')
        graph = analyze(self.repo)
        self.assertEqual({n['name'] for n in graph['nodes'] if n['changed']}, {'f', 'fresh'})
        self.assertTrue(graph['warnings'])

    def test_invalid_refs_and_depth(self):
        self.write('p.py', 'x = 1\n')
        self.commit()
        for kwargs in [{'base': '--help'}, {'base': 'missing'}, {'depth': 3}]:
            with self.assertRaises(ValueError):
                analyze(self.repo, **kwargs)

    def test_module_level_change_and_deletion_only(self):
        self.write('p.py', 'VALUE = 1\ndef f():\n    a = 1\n    return a\n')
        self.commit()
        self.write('p.py', 'VALUE = 2\ndef f():\n    return 1\n')
        graph = analyze(self.repo)
        self.assertEqual({n['qualname'] for n in graph['nodes'] if n['changed']}, {'<module>', 'f'})


if __name__ == '__main__':
    unittest.main()
