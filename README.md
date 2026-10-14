# diff_code — PLISM Codegraph PoC

差分を読みながら変更の位置・呼び出し関係を確認するローカルツールです。PythonとJavaScriptの部分的な静的解析を使い、AI/APIへの送信は行いません。

## 起動

必要なもの: Python 3.10以上、Git、Node.js（JavaScript解析用）、ブラウザ。依存ライブラリは同梱し、pip/npmの追加インストールは不要です。

```powershell
git clone https://github.com/soragaaoin-lang/diff_code.git
cd diff_code
python create_poc_demo.py demo-repo
python -m codegraph.poc --repo demo-repo --base HEAD~1 --head HEAD --port 8766
```

http://127.0.0.1:8766/ を開いてください。デモ作成先は新規ディレクトリを指定します。既存のディレクトリは上書きしません。終了はCtrl+C。

任意のローカルGitリポジトリの場合:

```powershell
python -m codegraph.poc --repo "C:\path\to\repository" --base HEAD~1 --head HEAD --port 8766
```

比較する2つのコミットを指定します。起動時の版を固定するため、変更する場合はサーバーを再起動してください。作業中の未コミットファイルは対象外です。

## 現在の画面

- 左: 変更ファイル一覧と検索。
- 中央: 前後の行番号、追加 `+` / 削除 `−`、変更前後3行の文脈を含む差分。全文表示・改行を含む検索も可能。
- 全文のスクロールバー横: 追加/削除の位置とクリック移動。
- 右: 関係グラフ、構造に基づく説明、使用箇所、重複候補、解析範囲。
- コード行のクリック: その行を含む関数を右のグラフの中心に表示。
- 円の大きさ: 行数・異なる呼び出し元関数数・異なる呼び出し先関数数。
- 静的な呼び出し元方向に1〜2 hopの影響候補を表示。

## 限界

JavaScriptは同一ファイルのトップレベル関数の直接呼び出しが中心です。動的な呼び出し・import先・メソッドなどは完全には解決できません。解析失敗や未対応ファイルを画面で表示します。解析に失敗しても本文・差分は読めます。

重複検出は構文一致と限定的な名前変更に対応。切り出しの安全性や意味の一致は保証しません。設計意図の自動生成は未実装です。「コードに基づく説明」は静的解析結果の定型表示です。

## テスト

```powershell
python -m unittest discover -s tests -v
node --check codegraph/poc_static/app.js
node --check codegraph/poc_js.cjs
```

## 構成・資料

- `codegraph/poc.py`: 標準HTTPサーバー、ローカル接続のみ
- `codegraph/poc_analysis.py`, `poc_js.cjs`: 解析・指標・重複検出
- `codegraph/poc_static/`: 現行PoC画面
- `codegraph/poc_vendor/`: Acornとライセンス
- `tests/`: テスト
- [詳細と実装時の検証記録](README-POC-v03.md)
- [要件・設計資料](docs/README.md)
- [従来版の説明](docs/legacy-readme.md)
- [同梱ライブラリ](THIRD_PARTY.md): Cytoscape.js。Acorn 8.15.0のMITライセンスは `codegraph/poc_vendor/ACORN-LICENSE`。

`README-POC-v03.md` と一部設計資料には開発時のローカルパスや過去の画面構成が含まれます。新規環境での起動はこのREADMEを参照してください。
