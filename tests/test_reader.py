import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from codegraph.reader import snapshot, file_diff, public, MAX_BYTES
from codegraph.notes import load_notes


class ReaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.git('init')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        self.write('p.py', 'def a():\n    return 1\ndef b():\n    return a()\n')
        self.write('説明.md', 'before\n')
        self.write('removed.txt', 'remove me\n')
        self.base = self.commit()
        self.write('p.py', 'def a():\n    return 2\ndef b():\n    return 0\n')
        self.write('説明.md', 'before\nafter\n')
        self.write('empty.txt', '')
        (self.repo / 'removed.txt').unlink()
        self.head = self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL).decode().strip()

    def write(self, path, text):
        (self.repo / path).write_text(text, encoding='utf-8')

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def snap(self):
        return snapshot(self.repo, self.base, self.head)

    def test_all_files_and_fixed_source(self):
        s = self.snap()
        self.assertEqual({f['file'] for f in s['files']}, {'p.py', '説明.md', 'empty.txt', 'removed.txt'})
        self.write('説明.md', 'uncommitted')
        f = file_diff(s, '説明.md')
        self.assertEqual(f['head']['lines'], ['before', 'after'])
        self.assertEqual(f['blocks'][-1]['kind'], 'insert')
        self.assertNotIn('_trees', public(s))
        json.dumps(public(s))

    def test_absence_empty_and_deleted(self):
        s = self.snap()
        self.assertEqual(file_diff(s, 'empty.txt')['head']['state'], 'ready')
        self.assertEqual(file_diff(s, 'empty.txt')['base']['state'], 'absent')
        self.assertEqual(file_diff(s, 'removed.txt')['base']['lines'], ['remove me'])
        self.assertEqual(file_diff(s, 'removed.txt')['head']['state'], 'absent')

    def test_graphs_are_separate(self):
        s = self.snap()
        self.assertEqual(len(s['graphs']['base']['edges']), 1)
        self.assertEqual(len(s['graphs']['head']['edges']), 0)

    def test_identity_changes_for_new_commit_with_same_content(self):
        old = self.snap()
        self.git('commit', '--allow-empty', '-m', 'new version')
        new = snapshot(self.repo, self.base, 'HEAD')
        self.assertNotEqual(old['meta']['snapshot_id'], new['meta']['snapshot_id'])

    def test_invalid_refs_and_paths(self):
        for ref in ['--help', 'WORKTREE', 'missing']:
            with self.assertRaises(ValueError):
                snapshot(self.repo, self.base, ref)
        with self.assertRaises(ValueError):
            file_diff(self.snap(), '../outside.txt')

    def test_binary_large_and_final_newline(self):
        (self.repo / 'binary.dat').write_bytes(b'\0data')
        self.write('large.txt', 'x' * (MAX_BYTES + 1))
        self.write('説明.md', 'before')
        self.head = self.commit()
        s = self.snap()
        self.assertEqual(file_diff(s, 'binary.dat')['head']['state'], 'binary')
        self.assertEqual(file_diff(s, 'large.txt')['head']['state'], 'too_large')
        self.assertFalse(file_diff(s, '説明.md')['head']['final_newline'])

    def test_reverse_unrelated_and_merge_commits(self):
        reverse = snapshot(self.repo, self.head, self.base)
        self.assertEqual(next(f for f in reverse['files'] if f['file'] == 'empty.txt')['status'], 'deleted')
        tree = self.git('rev-parse', 'HEAD^{tree}')
        unrelated = self.git('commit-tree', tree, '-m', 'unrelated root')
        merged = self.git('commit-tree', tree, '-p', self.head, '-p', unrelated, '-m', 'merge')
        self.assertEqual(snapshot(self.repo, self.head, unrelated)['files'], [])
        self.assertTrue(snapshot(self.repo, self.base, merged)['files'])

    def test_notes_reject_mismatch_and_skip_bad_item(self):
        meta = self.snap()['meta']
        path = self.repo / 'notes.json'
        data = dict(version=1, comparison=dict(repo=str(self.repo.resolve()), base=self.base, head=self.head, method='direct-v1'),
                    items=[dict(target='range', file='p.py', side='head', start=1, end=2, kind='code', text='説明', source='p.py:1-2'), {'text': 'invalid'}])
        path.write_text(json.dumps(data), encoding='utf-8')
        notes = load_notes(path, meta)
        self.assertEqual(len(notes['items']), 1)
        self.assertIn('1件', notes['warnings'][0])
        data['comparison']['head'] = self.base
        path.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(load_notes(path, meta)['items'], [])
        self.assertIn('別の比較', load_notes(path, meta)['warnings'][0])
        path.write_text('not json', encoding='utf-8')
        self.assertTrue(load_notes(path, meta)['warnings'])


if __name__ == '__main__':
    unittest.main()
