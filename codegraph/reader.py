"""Immutable, text-first review data; never executes repository code."""
import difflib
import hashlib
import io
import json
import tokenize
from pathlib import Path

from .analyzer import git, sources, index

MAX_BYTES = 1024 * 1024
MAX_FILES = 1000
MAX_LINES = 20000


def resolve(repo, ref):
    if not ref or ref.startswith('-') or ref == 'WORKTREE':
        raise ValueError('固定コミットまたはブランチ名を指定してください（WORKTREEは対象外）。')
    return git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()


def tree(repo, commit):
    result = {}
    for entry in git(repo, 'ls-tree', '-rz', commit).split(b'\0'):
        if not entry:
            continue
        metadata, path = entry.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        result[path.decode('utf-8', 'surrogateescape')] = (mode, kind, oid)
    return result


def source(snapshot, file, side):
    if side not in ('base', 'head'):
        raise ValueError('不正な比較側です。')
    entry = snapshot['_trees'][side].get(file)
    if not entry:
        return dict(state='absent', lines=[], reason='この版には存在しません。')
    mode, kind, oid = entry
    if kind != 'blob' or mode == '120000':
        return dict(state='unsupported', lines=[], reason='シンボリックリンク／サブモジュールは本文表示の対象外です。')
    repo = snapshot['meta']['repo']
    size = int(git(repo, 'cat-file', '-s', oid))
    if size > MAX_BYTES:
        return dict(state='too_large', lines=[], reason='1MBの表示上限を超えています。', bytes=size)
    raw = git(repo, 'cat-file', 'blob', oid)
    if b'\0' in raw:
        return dict(state='binary', lines=[], reason='バイナリのためテキスト差分を表示できません。')
    try:
        encoding = tokenize.detect_encoding(io.BytesIO(raw).readline)[0] if file.endswith('.py') else 'utf-8-sig'
        text = raw.decode(encoding)
    except (UnicodeError, SyntaxError, LookupError):
        return dict(state='unsupported', lines=[], reason='対応する文字コードで読み込めません。')
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        return dict(state='too_large', lines=[], reason='20,000行の表示上限を超えています。')
    return dict(state='ready', lines=lines, final_newline=text.endswith(('\n', '\r')), bytes=size)


def file_diff(snapshot, file):
    if file not in snapshot['_trees']['base'] and file not in snapshot['_trees']['head']:
        raise ValueError('この比較に含まれないパスです。')
    before, after = source(snapshot, file, 'base'), source(snapshot, file, 'head')
    result = dict(file=file, base=before, head=after, blocks=[])
    if before['state'] not in ('ready', 'absent') or after['state'] not in ('ready', 'absent'):
        return result
    a, b = before['lines'], after['lines']
    # Autojunk bounds repeated-line matching on large files; original lines remain available.
    result['blocks'] = [dict(kind=tag, old_start=i, old_end=j, new_start=k, new_end=l)
                        for tag, i, j, k, l in difflib.SequenceMatcher(None, a, b).get_opcodes()]
    return result


def snapshot(repo, base, head, with_graphs=True):
    repo = Path(repo).resolve()
    base_commit, head_commit = resolve(repo, base), resolve(repo, head)
    trees = dict(base=tree(repo, base_commit), head=tree(repo, head_commit))
    counts = {}
    for entry in git(repo, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--numstat', '-z', base_commit, head_commit).split(b'\0'):
        if entry:
            added, removed, path = entry.split(b'\t', 2)
            counts[path.decode('utf-8', 'surrogateescape')] = (int(added) if added != b'-' else None,
                                                             int(removed) if removed != b'-' else None)
    files = []
    for file in sorted(trees['base'].keys() | trees['head'].keys()):
        a, b = trees['base'].get(file), trees['head'].get(file)
        if a != b:
            added, removed = counts.get(file, (0, 0))
            files.append(dict(file=file, status='added' if a is None else 'deleted' if b is None else 'modified',
                              old_file=file if a is not None else None, new_file=file if b is not None else None,
                              added=added, removed=removed))
    if len(files) > MAX_FILES:
        raise ValueError('変更ファイルが1,000件を超えるため、この比較を表示できません。比較範囲を絞ってください。')
    graphs = graph_data(repo, base_commit, head_commit) if with_graphs else None
    identity = [str(repo), base_commit, head_commit, 'direct-v1']
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return dict(meta=dict(repo=str(repo), base=base, head=head, base_commit=base_commit,
                          head_commit=head_commit, method='direct-v1', snapshot_id=key), files=files, graphs=graphs, _trees=trees)


def public(snapshot):
    return {key: value for key, value in snapshot.items() if not key.startswith('_')}


def graph_data(repo, base_commit, head_commit):
    graphs, texts = {}, {}
    for side, commit in [('base', base_commit), ('head', head_commit)]:
        texts[side] = sources(repo, commit)
        nodes, edges, warnings, unresolved = index(texts[side])
        graphs[side] = dict(nodes=list(nodes.values()), edges=edges, warnings=warnings, unresolved=unresolved)
    maps = {side: {n['id']: n for n in g['nodes']} for side, g in graphs.items()}
    def body(side, n):
        return texts[side][n['file']].splitlines()[n['line']-1:n['end_line']]
    for side, other in [('base', 'head'), ('head', 'base')]:
        for n in graphs[side]['nodes']:
            counterpart = maps[other].get(n['id'])
            n['change'] = ('削除' if side == 'base' else '追加') if counterpart is None else ('変更' if body(side, n) != body(other, counterpart) else '通常')
    return graphs
