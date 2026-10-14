# PLISM Change Review

Repository: C:\Users\muto1\coderabbit\demo-repo
Base: main (4d869028f3e551039e0cf8cd60ca258ceb410a70)
Head: WORKTREE (WORKTREE)
Snapshot: b3972812470480b4e9c27dd6013c1e1c4cf38a8ea30fc23190e20be46debee43
Impact depth: 2

静的解析による確認候補です。確認済みは利用者の記録であり、承認・安全性の保証ではありません。

## 変更ファイル

- pipeline.py (modified): +1 / -1

## 確認する順番

- [ ] normalize_event — pipeline.py:4 (変更)
- [ ] build_projection — pipeline.py:8 (影響候補 1 hop)
  - build_projection → normalize_event — pipeline.py:9 normalize_event(event)
- [ ] export_analysis — pipeline.py:12 (影響候補 2 hop)
  - export_analysis → build_projection — pipeline.py:13 build_projection(events)
  - build_projection → normalize_event — pipeline.py:9 normalize_event(event)

## 静的チェック

ルールに該当する確認ポイントはありません。意味的なバグがないことを示すものではありません。

## 解析メモ

未解決call: 2
