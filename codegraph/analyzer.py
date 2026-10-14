from __future__ import annotations

import ast
import copy
import difflib
import hashlib
import json
import subprocess
import tokenize
from collections import defaultdict, deque
from pathlib import Path

EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'site-packages', 'build', 'dist'}


def git(repo, *args):
    result = subprocess.run(['git', '-c', 'core.quotepath=false', '-C', str(repo), *args], capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.decode('utf-8', 'replace').strip())
    return result.stdout


def sources(repo, ref):
    if ref == 'WORKTREE':
        result = {}
        for p in sorted(repo.rglob('*.py')):
            if any(part in EXCLUDED for part in p.relative_to(repo).parts) or p.is_symlink():
                continue
            if not p.resolve().is_relative_to(repo):
                continue
            try:
                with tokenize.open(p) as stream:
                    result[p.relative_to(repo).as_posix()] = stream.read()
            except (OSError, UnicodeError, SyntaxError):
                result[p.relative_to(repo).as_posix()] = '\x00'
        return result
    paths = git(repo, 'ls-tree', '-r', '--name-only', '-z', ref).decode('utf-8', 'surrogateescape').split('\0')
    result = {}
    for path in paths:
        if path.endswith('.py') and not any(part in EXCLUDED for part in Path(path).parts):
            raw = git(repo, 'show', f'{ref}:{path}')
            try:
                import io
                encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                result[path] = raw.decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
            except (UnicodeError, SyntaxError):
                result[path] = '\x00'
    return result


def module_name(path):
    parts = Path(path).with_suffix('').parts
    if parts[0] == 'src':
        parts = parts[1:]
    if parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts)


def index(files):
    nodes, edges, warnings = {}, [], []
    lookup = defaultdict(list)
    contexts = []
    for file, source in files.items():
        module = module_name(file)
        try:
            tree = ast.parse(source, filename=file)
        except (SyntaxError, ValueError) as exc:
            warnings.append(f'{file}: parse error: {exc}')
            continue
        imports = {}
        package = module if file.endswith('__init__.py') else module.rpartition('.')[0]
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    imports[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
            elif isinstance(stmt, ast.ImportFrom):
                prefix = stmt.module or ''
                if stmt.level:
                    parts = package.split('.') if package else []
                    prefix = '.'.join(parts[:len(parts) - stmt.level + 1] + ([prefix] if prefix else []))
                for alias in stmt.names:
                    if alias.name != '*':
                        imports[alias.asname or alias.name] = '.'.join(filter(None, [prefix, alias.name]))
        def collect(body, scope='', parent=None):
            for stmt in body:
                if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Include definitions inside if/try blocks, without entering other definitions twice.
                    for _, value in ast.iter_fields(stmt):
                        if isinstance(value, list):
                            collect([x for x in value if isinstance(x, ast.stmt)], scope, parent)
                    continue
                qual = f'{scope}.{stmt.name}' if scope else stmt.name
                ident = f'{file}::{qual}'
                start = min([stmt.lineno] + [d.lineno for d in stmt.decorator_list])
                node = dict(id=ident, name=stmt.name, qualname=qual, module=module, file=file,
                            line=start, end_line=stmt.end_lineno, kind='class' if isinstance(stmt, ast.ClassDef) else 'function',
                            parent=parent, changed=False, deleted=False, changes=[])
                node['signature'] = (ast.unparse(stmt.args) + ' -> ' +
                                     (ast.unparse(stmt.returns) if stmt.returns else '')) if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
                nodes[ident] = node
                lookup[f'{module}.{qual}'].append(ident)
                contexts.append((node, stmt, imports, source))
                collect(stmt.body, qual, ident)
        module_id = f'{file}::<module>'
        nodes[module_id] = dict(id=module_id, name=Path(file).name, qualname='<module>', module=module,
                               file=file, line=1, end_line=max(1, len(source.splitlines())), kind='module',
                               parent=None, changed=False, deleted=False, changes=[])
        contexts.append((nodes[module_id], tree, imports, source))
        collect(tree.body)

    unresolved = 0
    for node, tree, imports, source in contexts:
        calls = []
        shadowed = set()
        class Calls(ast.NodeVisitor):
            def visit_FunctionDef(self, child):
                if child is tree:
                    self.generic_visit(child)
            visit_AsyncFunctionDef = visit_FunctionDef
            def visit_ClassDef(self, child):
                if child is tree:
                    self.generic_visit(child)
            def visit_Call(self, call):
                calls.append(call)
                self.generic_visit(call)
            def visit_Name(self, name):
                if isinstance(name.ctx, ast.Store):
                    shadowed.add(name.id)
            def visit_arg(self, arg):
                shadowed.add(arg.arg)
        Calls().visit(tree)
        for call in calls:
            def dotted(expr):
                if isinstance(expr, ast.Name):
                    return expr.id
                if isinstance(expr, ast.Attribute):
                    prefix = dotted(expr.value)
                    return f'{prefix}.{expr.attr}' if prefix else ''
                return ''
            name = dotted(call.func)
            if not name:
                unresolved += 1
                continue
            candidates = []
            first, _, rest = name.partition('.')
            if first in shadowed and not (first in ('self', 'cls') and rest and node['parent'] and nodes[node['parent']]['kind'] == 'class'):
                unresolved += 1
                continue
            if first in imports:
                candidates.append(imports[first] + ('.' + rest if rest else ''))
            if first in ('self', 'cls') and rest:
                parent = node['qualname'].rpartition('.')[0]
                candidates.append(f"{node['module']}.{parent}.{rest}")
            elif first not in imports:
                scope = node['qualname'].split('.') if node['kind'] == 'function' else []
                for size in range(len(scope), -1, -1):
                    # Resolve local nested functions, but skip class namespaces.
                    prefix = '.'.join(scope[:size])
                    owner = nodes.get(f"{node['file']}::{prefix}")
                    if owner and owner['kind'] == 'class':
                        continue
                    candidates.append('.'.join([node['module']] + scope[:size] + [name]))
            target = None
            for candidate in candidates:
                matches = lookup.get(candidate, [])
                if len(matches) == 1:
                    target = matches[0]
                    break
            if target:
                edges.append(dict(id=f'e{len(edges)}', source=node['id'], target=target,
                                  file=node['file'], line=call.lineno,
                                  text=ast.get_source_segment(source, call) or name, type='call', deleted=False))
            else:
                unresolved += 1
    return nodes, edges, warnings, unresolved


def diff_changes(repo, base, head, old_files, new_files):
    # Git identifies tracked changes with NUL-delimited paths. Build hunks from
    # the exact analyzed snapshots so diffs and AST never disagree mid-edit.
    args = ['diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--name-only', '-z', base]
    if head != 'WORKTREE':
        args.append(head)
    args += ['--', '*.py']
    tracked = set(git(repo, *args).decode('utf-8', 'surrogateescape').split('\0'))
    paths = tracked | old_files.keys() | new_files.keys()
    changes, changed_files = [], []
    for file in sorted(paths):
        if file not in old_files and file not in new_files:
            continue
        before, after = old_files.get(file, ''), new_files.get(file, '')
        if before == after and (file in old_files) == (file in new_files):
            continue
        old_lines, new_lines = before.splitlines(keepends=True), after.splitlines(keepends=True)
        status = 'added' if file not in old_files else 'deleted' if file not in new_files else 'modified'
        added = removed = 0
        old_path = file if file in old_files else '/dev/null'
        for tag, a, a_end, b, b_end in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            old_count, count = a_end - a, b_end - b
            old_start, start = a + 1 if old_count else a, b + 1 if count else b
            patch = f'@@ -{old_start},{old_count} +{start},{count} @@\n'
            patch += ''.join('-' + line.rstrip('\r\n') + '\n' for line in old_lines[a:a_end])
            patch += ''.join('+' + line.rstrip('\r\n') + '\n' for line in new_lines[b:b_end])
            changes.append(dict(old_file=old_path, file=file, old_start=old_start, old_count=old_count,
                                start=start, count=count, patch=patch))
            added += count
            removed += old_count
        if not any(c['file'] == file for c in changes):
            changes.append(dict(old_file=old_path, file=file, old_start=0, old_count=0, start=0, count=0, patch=''))
        patch = ''.join(difflib.unified_diff(old_lines, new_lines, fromfile=f'Base/{file}', tofile=f'Head/{file}', n=3))
        changed_files.append(dict(file=file, status=status, added=added, removed=removed, patch=patch))
    return changes, changed_files


def apply_changes(nodes, old_nodes, changes):
    def intersect(node, start, count):
        return count > 0 and start <= node['end_line'] and start + count - 1 >= node['line']
    for change in changes:
        matches = [n for n in nodes.values() if n['file'] == change['file'] and
                   n['kind'] != 'module' and intersect(n, change['start'], change['count'])]
        previous = [n for n in old_nodes.values() if n['file'] == change['old_file'] and
                    n['kind'] != 'module' and intersect(n, change['old_start'], change['old_count'])]
        for prev in previous:
            if prev['id'] not in nodes:
                nodes[prev['id']] = {**prev, 'deleted': True, 'changes': []}
            matches.append(nodes[prev['id']])
        # Show a module change when changed lines lie outside all definitions.
        spans = [n for n in nodes.values() if n['file'] == change['file'] and n['kind'] != 'module' and not n['deleted']]
        outside = any(not any(n['line'] <= line <= n['end_line'] for n in spans)
                      for line in range(change['start'], change['start'] + change['count']))
        if not matches or outside:
            ident = f"{change['file']}::<module>"
            if ident not in nodes and ident in old_nodes:
                nodes[ident] = {**old_nodes[ident], 'deleted': True, 'changes': []}
            if ident in nodes:
                matches.append(nodes[ident])
        for n in {n['id']: n for n in matches}.values():
            n['changed'] = True
            n['changes'].append(change)


def impact(nodes, edges, depth):
    incoming = defaultdict(list)
    for edge in edges:
        incoming[edge['target']].append(edge)
    distance = {n['id']: 0 for n in nodes.values() if n['changed']}
    queue = deque(distance)
    highlighted = set()
    while queue:
        target = queue.popleft()
        if distance[target] >= depth:
            continue
        for edge in incoming[target]:
            highlighted.add(edge['id'])
            if edge['source'] not in distance:
                distance[edge['source']] = distance[target] + 1
                queue.append(edge['source'])
    return distance, highlighted


def graph_at_depth(graph, depth):
    if depth not in (1, 2):
        raise ValueError('depth must be 1 or 2')
    graph = copy.deepcopy(graph)
    nodes = {n['id']: n for n in graph['nodes']}
    distance, highlighted = impact(nodes, graph['edges'], depth)
    by_source = defaultdict(list)
    for edge in graph['edges']:
        edge['impact'] = edge['id'] in highlighted
        by_source[edge['source']].append(edge)
    for node in nodes.values():
        node['distance'] = distance.get(node['id'])
        node['affected'] = node['id'] in distance and not node['changed']
        path, current = [], node['id']
        while distance.get(current, 0) > 0:
            candidates = [e for e in by_source[current] if distance.get(e['target']) == distance[current] - 1]
            if not candidates:
                break
            edge = sorted(candidates, key=lambda e: (e['deleted'], e['file'], e['line'], e['id']))[0]
            path.append(edge['id'])
            current = edge['target']
        node['evidence_path'] = path
    graph['meta'].update(depth=depth, affected=sum(n['affected'] for n in nodes.values()))
    graph['review']['reading_order'] = [n['id'] for n in sorted(nodes.values(), key=lambda n: (n['distance'] or 0, n['file'], n['line'], n['id'])) if n['changed'] or n['affected']]
    return graph


def analyze(repo, base='HEAD', head='WORKTREE', depth=2):
    repo = Path(repo).resolve()
    if depth not in (1, 2):
        raise ValueError('depth must be 1 or 2')
    if not repo.is_dir():
        raise ValueError('Repository directory does not exist')
    # Resolve user refs to commits; option-like input never reaches git as a flag.
    def commit(ref):
        if not ref or ref.startswith('-'):
            raise ValueError('Invalid Git ref')
        return git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()
    base_commit = commit(base)
    head_commit = 'WORKTREE' if head == 'WORKTREE' else commit(head)
    root = Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    if repo != root:
        raise ValueError(f'Use repository root: {root}')
    old_files, new_files = sources(repo, base_commit), sources(repo, head_commit)
    old_nodes, old_edges, old_warnings, _ = index(old_files)
    nodes, edges, warnings, unresolved = index(new_files)
    parsed_files = {n['file'] for n in nodes.values()}
    changes, changed_files = diff_changes(repo, base_commit, head_commit, old_files, new_files)
    apply_changes(nodes, old_nodes, changes)
    for node in nodes.values():
        if node['deleted'] and node['file'] in new_files and node['file'] not in parsed_files:
            node.update(deleted=False, unparsed=True)
    # Preserve base evidence for removed symbols and calls to those symbols.
    deleted = {n['id'] for n in nodes.values() if n['deleted']}
    for edge in old_edges:
        if (edge['source'] in deleted or edge['target'] in deleted) and edge['source'] in nodes and edge['target'] in nodes:
            edges.append({**edge, 'id': f'e{len(edges)}', 'deleted': True})
    distance, highlighted = impact(nodes, edges, depth)
    by_source = defaultdict(list)
    for edge in edges:
        by_source[edge['source']].append(edge)
    def excerpt(node, files):
        if not node or node['file'] not in files:
            return None
        lines = files[node['file']].splitlines()
        selected = lines[node['line'] - 1:node['end_line']]
        return dict(line=node['line'], text='\n'.join(selected[:120]), truncated=len(selected) > 120)
    for n in nodes.values():
        n['affected'] = n['id'] in distance and not n['changed']
        n['distance'] = distance.get(n['id'])
        n['before'] = excerpt(old_nodes.get(n['id']), old_files)
        n['after'] = None if n['deleted'] or n.get('unparsed') else excerpt(n, new_files)
        path, current = [], n['id']
        while distance.get(current, 0) > 0:
            candidates = [e for e in by_source[current] if distance.get(e['target']) == distance[current] - 1]
            if not candidates:
                break
            edge = sorted(candidates, key=lambda e: (e['deleted'], e['file'], e['line'], e['id']))[0]
            path.append(edge['id'])
            current = edge['target']
        n['evidence_path'] = path
    for edge in edges:
        edge['impact'] = edge['id'] in highlighted
    snapshot = hashlib.sha256(json.dumps([str(repo), sorted(old_files.items()), sorted(new_files.items())],
                                        ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    from .review import build_review
    return dict(nodes=list(nodes.values()), edges=edges, changes=changes, changed_files=changed_files,
                review=build_review(nodes, old_nodes, new_files, changes),
                warnings=warnings + [f'BASE: {w}' for w in old_warnings],
                meta=dict(repo=str(repo), base=base, head=head, base_commit=base_commit, head_commit=head_commit,
                          depth=depth, files=len(new_files), changed=sum(n['changed'] for n in nodes.values()),
                          affected=sum(n['affected'] for n in nodes.values()), unresolved_calls=unresolved,
                          snapshot_id=snapshot))
