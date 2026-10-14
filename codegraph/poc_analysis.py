"""Bounded, side-separated analysis for the additional-requirements PoC."""
import ast
import copy
import hashlib
import io
import json
import subprocess
import tokenize
from collections import defaultdict
from pathlib import Path

from . import reader
from .analyzer import index, EXCLUDED

EXTENSIONS = {'.py': 'Python', '.js': 'JavaScript', '.mjs': 'JavaScript', '.cjs': 'JavaScript'}
MAX_SCAN = 150
MAX_TOTAL = 8 * 1024 * 1024
MAX_UNITS = 1200


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def python_units(file, text):
    tree = ast.parse(text)
    units = []
    lines = text.splitlines()

    def visit(parent, prefix=''):
        for fn in ast.iter_child_nodes(parent):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + fn.name
                body = fn.body
                parameters = [a.arg for a in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]]
                parameters += [a.arg for a in (fn.args.vararg, fn.args.kwarg) if a]
                locals_ = list(dict.fromkeys(parameters + [n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)]))
                bindings = {name: '$local' + str(i) for i, name in enumerate(locals_)}
                forbidden = (ast.Global, ast.Nonlocal, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
                safe = not any(isinstance(n, forbidden) or n is not fn and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in ast.walk(fn))
                class Rename(ast.NodeTransformer):
                    def visit_Name(self, n):
                        n.id = bindings.get(n.id, n.id)
                        return n
                regions = [('whole', body)] + ([('block'+str(i), body[i:i+3]) for i in range(len(body)-2)] if len(body) != 3 else [])
                for tag, statements in regions:
                    if len(statements) < 3:
                        continue
                    start, end = statements[0].lineno, statements[-1].end_lineno
                    source = '\n'.join(lines[start-1:end])
                    count = sum(t.type not in (tokenize.ENCODING, tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER) for t in tokenize.generate_tokens(io.StringIO(source).readline))
                    if count < 20:
                        continue
                    wrapper = ast.Module(body=statements, type_ignores=[])
                    units.append(dict(file=file, owner=name, tag=tag, start=start, end=end, text=source,
                                      type1=ast.dump(wrapper), type2=ast.dump(Rename().visit(copy.deepcopy(wrapper))) if safe else None,
                                      bindings=bindings, parameters=parameters, language='Python'))
                visit(fn, name+'.')
            elif isinstance(fn, ast.ClassDef):
                visit(fn, prefix+fn.name+'.')
    visit(tree)
    return units


def metrics(nodes, edges):
    functions = {n['id'] for n in nodes if n['kind'] == 'function'}
    for n in nodes:
        incoming = [e for e in edges if e['target'] == n['id']]
        outgoing = [e for e in edges if e['source'] == n['id']]
        n['metrics'] = dict(lines=n['end_line']-n['line']+1,
                            incoming=len({e['source'] for e in incoming if e['source'] in functions and e['source'] != n['id']}) if n['id'] in functions else None,
                            outgoing=len({e['target'] for e in outgoing if e['target'] in functions and e['target'] != n['id']}) if n['id'] in functions else None,
                            incoming_sites=len(incoming), outgoing_sites=len(outgoing),
                            self_calls=sum(e['source'] == e['target'] for e in outgoing),
                            other_incoming=sum(e['source'] not in functions for e in incoming))


def analyze_side(snapshot, side):
    texts, coverage, total = {}, [], 0
    for file in sorted(snapshot['_trees'][side]):
        ext = Path(file).suffix.lower()
        if any(p in EXCLUDED for p in Path(file).parts):
            coverage.append(dict(file=file, state='excluded', reason='除外ディレクトリ'))
            continue
        if ext not in EXTENSIONS:
            coverage.append(dict(file=file, state='unsupported', reason='構文解析はPython/JavaScriptのみ。取得できる本文は差分・検索可能。'))
            continue
        if len(texts) >= MAX_SCAN or total >= MAX_TOTAL:
            coverage.append(dict(file=file, state='not_run', reason='解析ファイル数／総サイズ上限'))
            continue
        src = reader.source(snapshot, file, side)
        if src['state'] != 'ready':
            coverage.append(dict(file=file, state=src['state'], reason=src.get('reason', '取得失敗')))
            continue
        total += src['bytes']
        if total > MAX_TOTAL:
            coverage.append(dict(file=file, state='not_run', reason='総サイズ上限'))
            continue
        texts[file] = '\n'.join(src['lines'])
    py = {f: t for f, t in texts.items() if f.endswith('.py')}
    nodes, edges, warnings, unresolved = index(py)
    nodes = list(nodes.values())
    units = []
    for f, t in py.items():
        try:
            units.extend(python_units(f, t))
            coverage.append(dict(file=f, state='partial', reason='Python AST。動的呼び出しは未解決。型2はローカル改名の限定版。'))
        except (SyntaxError, tokenize.TokenError, IndentationError, RecursionError) as exc:
            coverage.append(dict(file=f, state='failed', reason=str(exc)))
    js = {f: t for f, t in texts.items() if not f.endswith('.py')}
    if js:
        try:
            run = subprocess.run(['node', str(Path(__file__).with_name('poc_js.cjs'))], input=json.dumps(js), capture_output=True, text=True, encoding='utf-8', timeout=30)
            if run.returncode:
                raise ValueError(run.stderr[:500])
            for f, data in json.loads(run.stdout).items():
                nodes.extend(data['nodes']); edges.extend(data['edges']); units.extend(data['units'])
                warnings.extend(data['warnings']); unresolved += data['unresolved']
                coverage.append(dict(file=f, state=data['state'], reason='同一ファイルのトップレベル関数への直接呼び出しのみ解決。import/メソッド/JSX/TypeScript対象外。'))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            warnings.append('JavaScript解析失敗: '+str(exc))
            coverage.extend(dict(file=f, state='failed', reason='JavaScriptパーサーを実行できません') for f in js)
    for i, e in enumerate(edges):
        e.update(id=side+':'+str(i), side=side, end_line=e.get('end_line', e['line']))
    for n in nodes:
        n['language'] = EXTENSIONS.get(Path(n['file']).suffix, 'Python')
        n['body_hash'] = fingerprint('\n'.join(texts[n['file']].splitlines()[n['line']-1:n['end_line']]))
    metrics(nodes, edges)
    if len(units) > MAX_UNITS:
        warnings.append('重複解析単位を1200領域で打ち切りました。')
    return dict(nodes=nodes, edges=edges, unresolved=unresolved, warnings=warnings, coverage=coverage,
                units=units[:MAX_UNITS], file_hashes={f: fingerprint(t) for f, t in texts.items()})


def duplicate_groups(sides):
    groups = {}
    for side, data in sides.items():
        groups[side] = defaultdict(list)
        for u in data['units']:
            for kind in ('type1', 'type2'):
                if u[kind]:
                    key = (u['language'], kind, fingerprint(u[kind]))
                    groups[side][key].append(u)
    result, seen = [], set()
    for side in ('head', 'base'):
        for key, raw in sorted(groups[side].items(), key=lambda item: (item[0][1], -max(u['end']-u['start'] for u in item[1]))):
            members = []
            for u in raw:
                if not any(m['file'] == u['file'] and not (u['end'] < m['start'] or u['start'] > m['end']) for m in members):
                    members.append(u)
            if len(members) < 2:
                continue
            identities = tuple(sorted((u['file'], u['start'], u['end']) for u in members))
            signature = (side, identities)
            if signature in seen:
                continue
            seen.add(signature)
            other = groups['base' if side == 'head' else 'head'].get(key, [])
            old_ids = {(u['file'], u['owner'], u['tag']) for u in other}
            if len(other) < 2:
                state = '新規候補' if side == 'head' else '解消候補'
            elif all((u['file'], u['owner'], u['tag']) in old_ids for u in members):
                state = '既存'
            else:
                state = '対応不明・増加候補'
            if side == 'base' and len(other) >= 2:
                continue
            other_side = sides['base' if side == 'head' else 'head']
            if any(c['state'] in ('failed', 'not_run', 'too_large') and EXTENSIONS.get(Path(c['file']).suffix) == key[0] for c in other_side['coverage']) or other_side['warnings'] and any('打ち切り' in w for w in other_side['warnings']):
                state = '比較の解析不足・判定不可'
            result.append(dict(kind=key[1], language=key[0], side=side, state=state,
                               members=[{k: v for k, v in u.items() if k not in ('type1', 'type2')} for u in members[:8]],
                               total=len(members), hash=key[2]))
    return sorted(result, key=lambda g: (g['state'] == '既存', g['side'], g['kind']))[:100]


def analyze(snapshot):
    sides = {side: analyze_side(snapshot, side) for side in ('base', 'head')}
    duplicates = duplicate_groups(sides)
    for side, other in [('base', 'head'), ('head', 'base')]:
        old = {n['id']: n for n in sides[other]['nodes']}
        for n in sides[side]['nodes']:
            peer = old.get(n['id'])
            n['change'] = ('削除' if side == 'base' else '追加') if peer is None else ('変更' if n['body_hash'] != peer['body_hash'] else '通常')
        del sides[side]['units']
    return dict(sides=sides, duplicates=duplicates, limits=dict(files=MAX_SCAN, bytes=MAX_TOTAL, units=MAX_UNITS, groups=100),
                method='poc-v03: declaration/body AST; conservative local renaming; metrics count distinct functions; file-change labels')
