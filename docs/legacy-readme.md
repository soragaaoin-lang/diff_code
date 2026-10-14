# PLISM Change Review v1

差分を読む前に、変更の位置と呼び出し元への波及候補を掴む、Python向けローカルツールです。
標準ライブラリのHTTPサーバー＋AST＋同梱Cytoscape.js。Python依存パッケージのインストールは不要です。
解析対象のコードを実行したり、書き換えたりしません。

CodeRabbitのCodegraphを参考に、ローカルで変更を理解し確認するMVPです。
要件定義・方式検討・機能仕様・設計・試験結果は [docs/](docs/) にあります。
「rabbitcode」が指す製品と最終AIレビュー範囲は確認中。今回のレビュー候補は静的ルールです。

## v1で追加した機能

- 変更→1 hop→2 hopの確認一覧、確認済みのブラウザ保存
- 影響候補ごとの変更に至るcall経路とfile/line
- 定義のBase / Headコード（最大120行ずつ）、変更ファイルの差分
- 引数定義の変更、可変デフォルト引数、bare except、eval/execの静的確認ポイント
- 確認状況を含むブラウザMarkdownダウンロード、CLIのMarkdown出力
- 内容ベースのsnapshot IDによる古い確認済みの流用防止

```powershell
python -m codegraph --repo .\demo-repo --base main --report review.md
```

確認済みは人が読んだという記録で、レビュー承認や安全性の保証ではありません。
意味的バグを推論するLLMレビューは含みません。

## 必要なもの

- Python 3.10以上、Git、モダンブラウザ
- 解析対象はコミットが1つ以上あるGitリポジトリのルート
- Windows PowerShellでは `python` と `git` が利用できること

## 起動（Windows）

```powershell
cd C:\Users\muto1\coderabbit
python -m codegraph --repo "C:\path\to\plism" --base main --head WORKTREE --depth 2 --open
```

`C:\path\to\plism` は実際のplismリポジトリのパスに置き換えます。
ブラウザで http://127.0.0.1:8765 を開きます。終了はターミナルで Ctrl+C。
待ち受けは127.0.0.1のみ。起動後の外部ネット接続・アカウント登録は不要です。
ポートが使われている場合は `--port 8766` を指定してください。

### すぐ試せるデモ

```powershell
cd C:\Users\muto1\coderabbit
python setup_demo.py
python -m codegraph --repo .\demo-repo --base main --head WORKTREE --open
```

setup_demo.pyは新しい `demo-repo` にベースコミットと未コミット変更を作成します。
同名ディレクトリがある場合は停止し、既存内容を変更しません。
normalize_event（緑）→build_projection（白、1 hop）→export_analysis（白、2 hop）が見えます。
グラフの矢印は実際の呼び出し方向 caller → callee なので、影響を読むときは矢印を逆向きに辿ります。

### 比較方法

```powershell
# コミット間：表示するコードはHEADのスナップショット
python -m codegraph --repo "C:\path\to\plism" --base HEAD~1 --head HEAD

# HEADに対する作業ツリー：staged / unstaged / untracked Pythonを含む
python -m codegraph --repo "C:\path\to\plism"

# JSONを書き出して終了
python -m codegraph --repo .\demo-repo --base main --export demo.graph.json
```

デフォルトは `--base HEAD --head WORKTREE`。Gitのブランチ、タグ、コミットを利用できます。
UIのBase / Head欄も変更可能です。「再解析」で作業ツリーの更新を取り込みます。
比較は `git diff base head` に相当し、merge-base / 三点比較ではありません。

## UI

- 全コードベースの関数・async関数・クラス・モジュールを表示
- 通常は暗色、変更は緑、呼び出し元への影響候補と経路は白系
- 1 / 2 hop切替、名前・ファイル検索、ホイールズーム、ドラッグでパン、全体ボタン
- ノードクリックでfile / line、callers / callees、呼び出し行の根拠、差分hunkの旧／新行範囲と増減を表示
- 削除された定義はBaseのノードと呼び出し経路を破線表示。位置と根拠もBaseの行番号
- モジュールノードは関数／クラス外の変更・呼び出しを表現
- AST構文エラーは解析メモに表示して他ファイルの解析を継続

## 解析仕様とMVPの限界

ASTの定義範囲とGitの差分hunkが重なる定義を変更ノードにします。
クラス／外側関数の範囲に含まれる変更は、それらも変更として表示します。
行削除のみでもBaseの定義範囲から判定します。差分行の増減はhunk単位であり、関数専用の正確な増減数ではありません。
Gitの変更パスと取得したソースを使ってhunkを構成します。CRLF/LFは正規化し、改行形式だけの差は変更ノードにしません。
リネームは旧ファイル削除＋新ファイル追加として扱います。

直接の関数名、import alias、相対import、self / clsのメソッド、入れ子の関数を保守的に解決します。
解決できない呼び出しを名前の一致だけで他モジュールへ接続しません。
動的dispatch、インスタンス型推論、継承、super、再export、関数の別名代入、ローカルimport、デコレータの実行、クラス生成から__init__への暗黙の呼び出しは未対応です。
モジュールのimport依存やデータ依存の影響伝播も未対応。影響候補は解決できたcall辺の逆方向のみを辿ります。
モジュール名が衝突する場合は未解決として扱います。`src/`配置と通常のパッケージ配置に対応します。
削除した関数の影響候補はBaseの呼び出しから計算するため、Headで呼び出しが除去済みのものも含む場合があります。

`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`, `site-packages`, `build`, `dist` は除外。
作業ツリーではそれ以外のPythonファイル（gitignore済みを含む）を走査します。
大規模リポジトリ向けの増分解析／表示最適化は未実装。まず数百ノード程度のPoC検証を想定しています。
外部LLM、Bitbucket、Jira、Decision連携は含みません。

## テスト

```powershell
python -m unittest discover -s tests -v
```

一時Gitリポジトリを使い、1/2 hop、根拠行、削除、コミットスナップショット、import／メソッド／入れ子、未追跡ファイル、日本語パス、構文エラー、無効なrefを検証します。

## ファイル構成

```text
codegraph/
  __init__.py
  __main__.py             # CLI / local HTTP / JSON export
  analyzer.py             # AST / Git diff / impact
  review.py               # local static rules / reading order
  report.py               # Markdown output
  static/
    index.html
    style.css
    app.js
    vendor/
      cytoscape.min.js
      CYTOSCAPE-LICENSE.txt
tests/test_analyzer.py
tests/test_review.py
docs/                     # requirements / usage / spec / design / test report
demo/pipeline.py
setup_demo.py
README.md
THIRD_PARTY.md
```

ブラウザライブラリはCytoscape.js 3.33.1（MIT）を同梱。詳細はTHIRD_PARTY.md。
