"""Deterministic review prompts, never presented as LLM review results."""
import ast


def build_review(nodes, old_nodes, files, changes):
    findings = {}
    def add(code, severity, file, line, message, suggestion):
        key = (file, line, code)
        findings[key] = dict(id=f'{file}:{line}:{code}', code=code, severity=severity,
                             file=file, line=line, message=message, suggestion=suggestion)
    for node in nodes.values():
        old = old_nodes.get(node['id'])
        if node['changed'] and not node['deleted'] and old and node['kind'] == 'function' and old.get('signature') != node.get('signature'):
            add('API_SIGNATURE_CHANGED', 'check', node['file'], node['line'],
                f"{node['qualname']} の引数・戻り値の定義が変わりました。",
                'callersの引数数・キーワード名・戻り値の利用を確認してください。')
    for file, source in files.items():
        ranges = [(c['start'], c['start'] + c['count'] - 1) for c in changes if c['file'] == file and c['count']]
        if not ranges:
            continue
        changed_line = lambda line: any(a <= line <= b for a, b in ranges)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            continue
        for stmt in ast.walk(tree):
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defaults = stmt.args.defaults + [d for d in stmt.args.kw_defaults if d is not None]
                for default in defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)) and changed_line(default.lineno):
                        add('MUTABLE_DEFAULT', 'warning', file, default.lineno,
                            '可変オブジェクトをデフォルト引数にしています。呼び出し間で共有されます。',
                            '共有が意図通りか確認し、必要ならNoneを初期値にして関数内で生成してください。')
            if isinstance(stmt, ast.ExceptHandler) and stmt.type is None and changed_line(stmt.lineno):
                add('BARE_EXCEPT', 'warning', file, stmt.lineno,
                    '例外の種類を指定せず捕捉しています。', '捕捉する例外型を限定できるか確認してください。')
            if isinstance(stmt, ast.Call) and isinstance(stmt.func, ast.Name) and stmt.func.id in ('eval', 'exec') and changed_line(stmt.lineno):
                add('DYNAMIC_EXECUTION', 'check', file, stmt.lineno,
                    f'{stmt.func.id} による動的実行があります。', '入力の出所と、動的実行を使わない方法を確認してください。')
    reading = sorted((n for n in nodes.values() if n['changed'] or n['affected']),
                     key=lambda n: (n['distance'] or 0, n['file'], n['line'], n['id']))
    return dict(engine='local-static-rules', reading_order=[n['id'] for n in reading],
                findings=[findings[key] for key in sorted(findings)])
