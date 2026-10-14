import test_analyzer as fixtures
from codegraph.analyzer import analyze, graph_at_depth, index
from codegraph.report import markdown_report


class ReviewTests(fixtures.AnalyzerTests):
    # Inherit repository fixture only, without running the base cases again.
    pass


for name in list(fixtures.AnalyzerTests.__dict__):
    if name.startswith('test_'):
        setattr(ReviewTests, name, None)


def test_snapshot_identity_and_depth(self):
    self.write('p.py', 'def a():\n    return 1\ndef b():\n    return a()\ndef c():\n    return b()\n')
    self.commit()
    self.write('p.py', 'def a():\n    return 2\ndef b():\n    return a()\ndef c():\n    return b()\n')
    two = analyze(self.repo)
    one = graph_at_depth(two, 1)
    self.assertEqual(two['meta']['snapshot_id'], one['meta']['snapshot_id'])
    self.assertEqual(two['meta']['affected'], 2)
    self.assertEqual(one['meta']['affected'], 1)
    node = next(n for n in two['nodes'] if n['name'] == 'c')
    self.assertEqual(len(node['evidence_path']), 2)
    edge_by_id = {e['id']: e for e in two['edges']}
    first, second = [edge_by_id[i] for i in node['evidence_path']]
    self.assertEqual(first['target'], second['source'])
    self.assertEqual(first['source'], node['id'])
    self.write('p.py', 'def a():\n    return 3\n')
    self.assertNotEqual(two['meta']['snapshot_id'], analyze(self.repo)['meta']['snapshot_id'])


def test_rules_only_on_changed_lines(self):
    self.write('p.py', 'def legacy(items=[]):\n    return items\n')
    self.commit()
    self.write('p.py', 'def legacy(items=[]):\n    return items\n\ndef fresh(items=[]):\n    try:\n        return eval("1")\n    except:\n        return items\n')
    graph = analyze(self.repo)
    findings = graph['review']['findings']
    self.assertEqual({f['code'] for f in findings}, {'MUTABLE_DEFAULT', 'BARE_EXCEPT', 'DYNAMIC_EXECUTION'})
    self.assertFalse(any(f['line'] == 1 for f in findings))


def test_signature_and_source_report(self):
    self.write('file with space.py', 'def f(x):\n    return x\n')
    self.commit()
    self.write('file with space.py', 'def f(x, y=0):\n    return x + y\n')
    graph = analyze(self.repo)
    node = next(n for n in graph['nodes'] if n['name'] == 'f')
    self.assertIn('def f(x):', node['before']['text'])
    self.assertIn('def f(x, y=0):', node['after']['text'])
    self.assertEqual(graph['changed_files'][0]['file'], 'file with space.py')
    self.assertIn('-def f(x):', graph['changed_files'][0]['patch'])
    self.assertEqual(graph['review']['findings'][0]['code'], 'API_SIGNATURE_CHANGED')
    report = markdown_report(graph, [node['id']])
    self.assertIn('- [x] f', report)
    self.assertIn('API_SIGNATURE_CHANGED', report)
    self.assertIn(graph['meta']['snapshot_id'], report)


def test_no_false_call_for_shadowed_parameter(self):
    nodes, edges, _, _ = index({'p.py': 'def f():\n    pass\ndef caller(f):\n    return f()\n'})
    self.assertFalse(any(nodes[e['source']]['name'] == 'caller' for e in edges))


def test_crlf_and_empty_added_file(self):
    (self.repo / 'p.py').write_bytes(b'def f():\r\n    return 1\r\n')
    self.commit()
    graph = analyze(self.repo)
    self.assertEqual(graph['meta']['changed'], 0)
    self.write('empty.py', '')
    graph = analyze(self.repo)
    self.assertEqual(graph['changed_files'][0]['status'], 'added')
    self.assertTrue(next(n for n in graph['nodes'] if n['file'] == 'empty.py')['changed'])


def test_head_syntax_error_is_not_a_deletion(self):
    self.write('p.py', 'def f():\n    return 1\n')
    self.commit()
    self.write('p.py', 'def f(:\n    return 1\n')
    graph = analyze(self.repo)
    node = next(n for n in graph['nodes'] if n['name'] == 'f')
    self.assertFalse(node['deleted'])
    self.assertTrue(node['unparsed'])
    self.assertIsNone(node['after'])
    self.assertTrue(graph['changed_files'])
    self.assertTrue(graph['warnings'])


for test in [test_snapshot_identity_and_depth, test_rules_only_on_changed_lines, test_signature_and_source_report,
             test_no_false_call_for_shadowed_parameter, test_crlf_and_empty_added_file, test_head_syntax_error_is_not_a_deletion]:
    setattr(ReviewTests, test.__name__, test)
