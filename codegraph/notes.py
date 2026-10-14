"""Human-authored notes scoped to an exact comparison."""
import json
from pathlib import Path


def load_notes(path, meta):
    result = dict(items=[], warnings=[], supplied=path is not None)
    if path is None:
        return result
    try:
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('読解メモは1MB以下にしてください。')
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('items'), list):
            raise ValueError('読解メモの形式が不正です。')
        comparison = data.get('comparison', {})
        if not isinstance(comparison, dict):
            raise ValueError('比較識別の形式が不正です。')
        if (str(Path(comparison.get('repo', '')).resolve()) != meta['repo'] or
                comparison.get('base') != meta['base_commit'] or comparison.get('head') != meta['head_commit'] or
                comparison.get('method') != 'direct-v1'):
            result['warnings'].append('この説明は別の比較用です。')
            return result
        invalid = 0
        for entry in data['items']:
            if not isinstance(entry, dict):
                invalid += 1
                continue
            ok = (entry.get('target') in ('comparison', 'file', 'definition', 'range') and
                  entry.get('kind') in ('author', 'code', 'inference') and
                  isinstance(entry.get('text'), str) and bool(entry['text'].strip()) and
                  isinstance(entry.get('source'), str) and bool(entry['source'].strip()))
            if entry.get('target') != 'comparison':
                ok = ok and isinstance(entry.get('file'), str) and bool(entry['file']) and entry.get('side') in ('base', 'head')
            if entry.get('target') in ('definition', 'range'):
                has_range = type(entry.get('start')) is int and type(entry.get('end')) is int and 1 <= entry['start'] <= entry['end']
                ok = ok and (has_range or entry.get('target') == 'definition' and isinstance(entry.get('definition'), str) and bool(entry['definition']))
            if ok:
                result['items'].append(entry)
            else:
                invalid += 1
        if invalid:
            result['warnings'].append(f'形式が不正な読解メモ {invalid}件を読み込みませんでした。')
    except (OSError, ValueError, TypeError) as exc:
        result['warnings'].append(f'読解メモを読み込めませんでした: {exc}')
    return result
