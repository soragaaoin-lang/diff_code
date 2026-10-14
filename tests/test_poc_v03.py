import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from codegraph import poc_analysis as a, reader

PY = '''def transform(value):
    adjusted = value + 2
    doubled = adjusted * 3
    offset = doubled - 1
    return offset + value + doubled

def caller(value):
    transform(value)
    return transform(value + 1)
'''
JS = '''export function transform(value) {
    const adjusted = value + 2;
    const doubled = adjusted * 3;
    const offset = doubled - 1;
    return offset + value + doubled;
}
export const caller = value => transform(value) + transform(value + 1);
function shadow(transform) { return transform(1); }
'''


class PoCTests(unittest.TestCase):
    def js(self, text):
        r = subprocess.run(['node', str(Path(a.__file__).with_name('poc_js.cjs'))], input=json.dumps({'sample.js': text}), text=True, encoding='utf-8', capture_output=True, check=True)
        return json.loads(r.stdout)['sample.js']

    def test_js_calls_distinct_and_shadowing(self):
        result = self.js(JS)
        a.metrics(result['nodes'], result['edges'])
        n = next(n for n in result['nodes'] if n['name'] == 'transform')
        self.assertEqual(n['metrics']['incoming'], 1)
        self.assertEqual(n['metrics']['incoming_sites'], 2)
        self.assertEqual(result['unresolved'], 1)
        self.assertTrue(all(e['source'].endswith('caller') for e in result['edges']))

    def test_js_failure_is_explicit(self):
        self.assertEqual(self.js('function broken( {')['state'], 'failed')

    def test_python_rename_preserves_literals(self):
        one = a.python_units('a.py', PY)[0]
        two = a.python_units('b.py', PY.replace('value', 'input_').replace('adjusted', 'first'))[0]
        three = a.python_units('c.py', PY.replace('value + 2', 'value + 99'))[0]
        self.assertNotEqual(one['type1'], two['type1'])
        self.assertEqual(one['type2'], two['type2'])
        self.assertNotEqual(one['type2'], three['type2'])

    def test_js_rename_preserves_property_names(self):
        one = self.js(JS)['units'][0]
        two = self.js(JS.replace('value','input_').replace('adjusted','first'))['units'][0]
        self.assertEqual(one['type2'], two['type2'])
        self.assertNotEqual(one['type1'], two['type1'])
        three = self.js(JS.replace('value + 2', 'value + 99'))['units'][0]
        self.assertNotEqual(one['type2'], three['type2'])

    def test_recursion_not_counted_as_other_caller(self):
        nodes=[dict(id='a',kind='function',line=1,end_line=4),dict(id='module',kind='module',line=1,end_line=6)]
        edges=[dict(source='a',target='a'),dict(source='module',target='a')]
        a.metrics(nodes,edges)
        self.assertEqual(nodes[0]['metrics']['incoming'],0)
        self.assertEqual(nodes[0]['metrics']['self_calls'],1)
        self.assertEqual(nodes[0]['metrics']['other_incoming'],1)

    def test_snapshot_mixed_language_diff_and_duplicates(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            repo=Path(tmp)
            self.assertTrue(repo.resolve().is_relative_to(Path.cwd().resolve()))
            def git(*args):
                return subprocess.check_output(['git','-C',tmp,*args],stderr=subprocess.DEVNULL).decode().strip()
            git('init');git('config','user.email','poc@example.invalid');git('config','user.name','PoC Test')
            (repo/'sample.py').write_text(PY,encoding='utf-8');(repo/'sample.js').write_text(JS,encoding='utf-8')
            git('add','.');git('commit','-m','base');base=git('rev-parse','HEAD')
            (repo/'clone.py').write_text(PY.replace('transform','replica').replace('value','item'),encoding='utf-8')
            (repo/'clone.js').write_text(JS.replace('transform','replica').replace('value','item'),encoding='utf-8')
            (repo/'broken.py').write_text('def broken(:\n',encoding='utf-8')
            (repo/'extra.css').write_text('a { color: red; }',encoding='utf-8')
            git('add','.');git('commit','-m','head');head=git('rev-parse','HEAD')
            snap=reader.snapshot(repo,base,head,with_graphs=False)
            self.assertEqual(reader.file_diff(snap,'broken.py')['head']['state'],'ready')
            result=a.analyze(snap)
            self.assertTrue(any(n['language']=='JavaScript' for n in result['sides']['head']['nodes']))
            self.assertTrue(any(c['file']=='broken.py' and c['state']=='failed' for c in result['sides']['head']['coverage']))
            self.assertTrue(any(c['file']=='extra.css' and c['state']=='unsupported' for c in result['sides']['head']['coverage']))
            self.assertTrue(any(g['kind']=='type2' and g['language']=='JavaScript' for g in result['duplicates']))
            self.assertTrue(any(g['kind']=='type2' and g['language']=='Python' for g in result['duplicates']))
            self.assertFalse(any(n['file']=='clone.js' for n in result['sides']['base']['nodes']))
            with self.assertRaises(ValueError):reader.file_diff(snap,'../secret')


if __name__=='__main__':unittest.main()
