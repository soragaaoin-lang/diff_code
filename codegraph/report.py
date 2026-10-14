def markdown_report(graph, reviewed=()):
    reviewed = set(reviewed)
    meta = graph['meta']
    nodes = {n['id']: n for n in graph['nodes']}
    edges = {e['id']: e for e in graph['edges']}
    lines = ['# PLISM Change Review', '', f"Repository: {meta['repo']}",
             f"Base: {meta['base']} ({meta['base_commit']})", f"Head: {meta['head']} ({meta['head_commit']})",
             f"Snapshot: {meta['snapshot_id']}", f"Impact depth: {meta['depth']}", '',
             '静的解析による確認候補です。確認済みは利用者の記録であり、承認・安全性の保証ではありません。', '', '## 変更ファイル', '']
    for file in graph['changed_files']:
        lines.append(f"- {file['file']} ({file['status']}): +{file['added']} / -{file['removed']}")
    lines += ['', '## 確認する順番', '']
    for ident in graph['review']['reading_order']:
        node = nodes[ident]
        label = '変更' if node['changed'] else f"影響候補 {node['distance']} hop"
        lines.append(f"- [{'x' if ident in reviewed else ' '}] {node['qualname']} — {node['file']}:{node['line']} ({label}{', Baseの削除定義' if node['deleted'] else ''})")
        for edge_id in node['evidence_path']:
            edge = edges[edge_id]
            text = edge['text'].replace('\n', ' ')
            lines.append(f"  - {nodes[edge['source']]['qualname']} → {nodes[edge['target']]['qualname']} — {edge['file']}:{edge['line']} {text}{' [Base]' if edge['deleted'] else ''}")
    lines += ['', '## 静的チェック', '']
    if not graph['review']['findings']:
        lines.append('ルールに該当する確認ポイントはありません。意味的なバグがないことを示すものではありません。')
    for finding in graph['review']['findings']:
        lines += [f"- [{finding['severity']}] {finding['code']} — {finding['file']}:{finding['line']}",
                  f"  {finding['message']}", f"  {finding['suggestion']}"]
    lines += ['', '## 解析メモ', '', f"未解決call: {meta['unresolved_calls']}"]
    lines += [f'- {warning}' for warning in graph['warnings']]
    return '\n'.join(lines) + '\n'
