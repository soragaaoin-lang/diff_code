# 機能仕様書 v1

## 画面

上部: repo比較のBase / Head、再解析、検索、depth 1/2。
メイン: Codegraphと全体／ズーム操作。右: ノード詳細とレビュー作業一覧。
レビュー作業一覧は変更定義、1 hop、2 hopの順。選択でグラフと詳細が同期する。
変更ファイルには差分を表示し、AST解析できないファイルも一覧から読む。
確認ポイントはseverity（warning / check）、説明、file/line、確認案を表示する。

## 状態

`snapshot_id`はrepo実パスとBase/Headコード内容からSHA-256で計算する。
depthはIDに含めない。Git ref表示名の変更でも内容が同じなら同じID。
確認済みnode IDの集合を `plism-review:<snapshot_id>` に保存。別スナップショットでは初期化。
depth 1で非表示の2 hopノードの記録は消さない。
読み取り失敗・構文エラー時は警告を示し、解析の完全性を保証しない。
再解析に失敗したときは前回結果を保持し、前回の比較を表示していることを示す。

## ノード詳細

- Node IDは `relative_file::qualname`。モジュールは `<module>`。
- 行番号は1始まり、末尾行を含む。削除ノードはBaseの位置。
- BaseとHeadの定義コードを最大120行ずつ表示。超過は切り詰めを明示。
- 差分hunkはBase／Headの行範囲と変更テキスト。増減はhunk全体。
- 影響候補は最短call経路を1本提示。複数候補の全経路はグラフ上で確認可能。
- callの矢印はcaller→callee、探索はcalleeからcallerへ。
- 削除済みの経路にはBase由来を表示し、Headで生きている経路と区別。

## 静的チェック

| コード | severity | 条件 | 意味 |
|---|---|---|---|
| API_SIGNATURE_CHANGED | check | 同一IDの関数の引数定義／戻り値annotationが変化 | callerとの互換性を人が確認 |
| MUTABLE_DEFAULT | warning | Headの変更行にlist/dict/setリテラルのデフォルト引数 | 呼び出し間で値が共有される可能性 |
| BARE_EXCEPT | warning | Headの変更行にtypeのないexcept | KeyboardInterrupt等も捕捉し得る |
| DYNAMIC_EXECUTION | check | Headの変更行にbare eval/exec呼び出し | 入力の出所と代替手段を確認 |

チェックは完全なSAST／意味的バグ検出ではない。意図的な共有やeval名の再定義等で偽陽性はあり得る。
外部ライブラリ、動的dispatch、import依存、型推論を含む完全な影響分析は対象外。
同じfile/line/ruleの指摘は重複排除する。変更していない既存行のルール違反は新規指摘しない。

## APIとCLI

`GET /api/graph?base=...&head=...&depth=1|2&refresh=1`。
正常200、無効ref／depth等400。不明パス404。起動時と同じrepoのみを解析する。
グラフJSONにnodes/edges/changes/warnings/metaを維持し、changed_files/reviewを追加する。
nodeにbefore/after/evidence_pathを追加。before/afterは `{line,text,truncated}` またはnull。
reviewにreading_order/findings、metaにsnapshot_idを追加。
changed_filesはfile/status/added/removed/patch。
辺IDは解析結果内で一意。永続IDとして利用しない。

`--export`はJSON出力、`--report`はMarkdown出力後終了。ブラウザのレポートは確認状況を含む。
CLIレポートはブラウザのlocalStorageを読み込まないため、確認状況は未確認として出力する。

## 受入試験

1. デモのnormalize_eventが変更として緑、callerがdepthに応じて白になる。
2. 影響候補クリックで変更ノードへのfile/line付き経路が出る。
3. 差分とBase/Headコードが一致する。削除ノードにHeadコードを表示しない。
4. 確認済み→再読込で復元。作業ツリー変更→再解析で以前の確認を流用しない。
5. ローカルルールに該当する変更が根拠付きで表示される。
6. Markdownが比較情報・経路・チェック・確認状況を含む。
7. 不正ref、空グラフ、構文エラー、無変更、保存不可の状態を扱える。
