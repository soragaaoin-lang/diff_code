# 試験計画・結果 v1

実施日: 2026-10-10 / 対象: PLISM Change Review v1

## 自動試験

コマンド: `python -m unittest discover -s tests -v`。
ステージング（Python 3.14.3）と配置先（Python 3.10.11）で各16件成功。JavaScriptは `node --check codegraph/static/app.js` で構文確認済み。

| 対応要件 | ケース | 結果 |
|---|---|---|
| R01/R03/R04 | WORKTREEの1/2 hopと根拠行 | 成功 |
| R03/R04 | 削除定義のBase経路保持 | 成功 |
| R01 | コミットHeadに作業ツリーを混ぜない | 成功 |
| R02 | alias／相対import／メソッド／入れ子 | 成功 |
| R03/R12 | 日本語パス、未追跡、構文エラー | 成功 |
| R01/R07 | 無効ref／depth拒否 | 成功 |
| R03 | モジュール変更と行削除 | 成功 |
| R04/R10 | 証拠経路、depth不変ID、内容変更でID更新 | 成功 |
| R09 | 3種類の追加ルールと既存違反の除外 | 成功 |
| R03/R06/R09/R11 | 空白パス、signature、Base/Head、確認済みレポート | 成功 |
| R02 | 同名引数で隠された関数に誤接続しない | 成功 |
| R03 | CRLF/LFと空ファイル追加 | 成功 |
| R12 | Head構文エラーを削除と誤表示しない | 成功 |
| R07/R10 | HTTP depthは同一snapshot、refreshは内容更新 | 成功 |
| R01/R07/N03 | HTTP400でも前回snapshot維持、静的200、未定義404 | 成功 |
| R11 | CLI JSON／Markdown出力 | 成功 |

## ブラウザ受入試験

実行環境: Windows、Codex内ブラウザ。既存demo-repoのmain→WORKTREEを使用。

| 対応要件 | 操作・観察 | 結果 |
|---|---|---|
| R05/R08 | 変更1ノード、影響2ノード、確認一覧3件 | 確認 |
| R06 | normalize_eventのhunkとBase/Headコード | 確認 |
| R04/R06 | build_projectionからnormalize_eventへのpipeline.py:9の経路 | 確認 |
| R07/R08 | depth 1で一覧2件・影響1件、depth 2で一覧3件・影響2件 | 確認 |
| R10 | normalize_event確認済み→再読込で1/3を維持 | 確認 |
| R11 | レポート保存→DownloadsのMarkdownに[x]、比較、経路を確認 | 確認 |

ダウンロード完了イベントの取得が操作ツールでタイムアウトしたが、実際の保存ファイルが存在し内容も正しいことを別途確認した。
depth切替時にレビュータブがノード詳細へ戻る問題を検出し、修正して再確認した。

## 未実施・限界

- 実plismの過去変更を使った評価（repoパス未指定）。
- 利用者の理解時間・正答率の比較、静的チェックの偽陽性率。
- 数千ノード以上の性能測定、3.10／3.14以外のPythonバージョンの検証。
- localStorage禁止環境、別ブラウザ・別OSでの手動検証。
- AIレビュー品質試験（外部LLM／ローカルLLMは現実装に含まれない）。

自動試験成功は上記ケースへの適合を示す。コードの全影響を漏れなく抽出したことや、理解時間が短縮したことまでは示さない。
