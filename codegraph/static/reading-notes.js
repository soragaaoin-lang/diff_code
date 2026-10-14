const HISTORY_COMPARISON={base:'e34e61ed71f70cf30f0e43c093333e8b6c7c3bc6',head:'244203cba1bc54fa65d88803a23a2bc6c8f8ca0c'};
const SERVICE='src/chat_history_poc/services/lightweight_decision_bundle_service.py';
const HISTORY_NOTES={
  [SERVICE]:{title:'会話から、Decision候補の周辺を取り出す',lead:'会話全体を渡す代わりに、提案・合意・変更・理由のヒントがあるメッセージと、その前後をまとめて解析用の入力にするサービスが追加されました。',behavior:'メッセージと添付内容を検索し、ヒットした位置の前後の範囲を統合します。選んだメッセージの原文・関連する添付・制約はコピーして保持します。',checks:'候補抽出の段階でDecisionの承認状態を決めることはありません。implementation_events は出力から除外されます。抽出の網羅性は unknown として扱われます。',refs:[['select',38,109],['export',111,157],['_validate',173,214]]},
  'src/chat_history_poc/cli.py':{title:'軽量抽出を、CLIから実行できるようにする',lead:'export-lightweight-analysis コマンドが追加されました。Projection v3 の入力から軽量な解析用バンドルを準備できます。',behavior:'parser が入力・出力先・前後に含めるメッセージ数などを受け取り、main が LightweightDecisionBundleService の export を呼びます。',checks:'この経路はAIの回答を生成する処理ではなく、ファイル交換用の入力を準備します。CLIからサービスへの連鎖した呼び出しは、現在のグラフ解析では一部未解決です。',refs:[['parser',47,70],['main',184,205]]},
  'tests/test_lightweight_decision_bundle.py':{title:'原文保持と、抽出境界を確認するテスト',lead:'軽量抽出のためのテストが追加されました。元データを変更しないこと、近接する範囲の統合、離れた変更メッセージや添付を拾うことなどを確認します。',behavior:'不正なEvidence、空の入力、出力ディレクトリの上書き拒否、CLIからの実行もテスト対象に含まれます。',checks:'ここに表示するのはテストコードの内容です。この対象リポジトリのテスト実行結果は今回取得していません。',refs:[['原文保持',35,46],['範囲統合',48,57],['出力とCLI',122,160]]},
  'src/chat_history_poc/__main__.py':{title:'変更されたCLIへの入口',lead:'このファイル自体に差分はありません。変更された main を呼んでいるため、1 hop の影響候補として表示されます。',behavior:'cli から main を読み込み、main() の戻り値を終了コードに使います。',checks:'ここから新しいコマンドへ入る経路を確認できます。候補としての表示であり、実行時の不具合を示しているわけではありません。',refs:[['main 呼び出し',1,4]]}
};
const FUNCTION_NOTES={
  'LightweightDecisionBundleService.select':['ヒントを探し、前後の会話をまとめる','入力を検証したあと、メッセージと添付内容に含まれるヒントを探します。添付にヒットした場合は親メッセージを起点にします。','前後の範囲を統合し、原文をコピーして返します。添付は、選択された親メッセージと関連するものを残します。'],
  'LightweightDecisionBundleService.export':['解析用バンドルをファイルに保存する','入力JSON・プロンプト・スキーマを読み込み、select で取り出した会話を保存します。AIへの通信は行いません。','出力先が空であることを確認し、入力・出力のハッシュとサイズを manifest に記録します。AI呼び出しの実施数は0として記録されます。'],
  'LightweightDecisionBundleService._hits':['文章からヒントの種類を返す','提案・合意・変更・理由の正規表現を文章に適用し、一致した種類の名前を返します。','この結果は候補の手掛かりです。承認済みなどの状態を確定するものではありません。'],
  'LightweightDecisionBundleService._ranges':['近い候補の範囲を統合する','ヒット位置の前後を会話の配列の範囲内に収め、重なる範囲と隣り合う範囲をひとつにまとめます。','離れた位置の範囲は別々に残します。'],
  'LightweightDecisionBundleService._validate':['入力とEvidenceの整合性を確認する','Projection v3、session_id、メッセージのactorとcontent、Evidence IDの一意性、添付の親IDなどを検証します。','条件に合わない入力は ProjectionInputError にします。'],
  'LightweightDecisionBundleService.__init__':['前後に含める件数と検索ルールを準備する','前後に含めるメッセージ数が0以上の整数か確認し、各ヒントの正規表現を準備します。','boolや負の数など、整数の件数として扱えない値は拒否します。'],
  'LightweightDecisionBundleService._encode':['JSONをUTF-8のバイト列にする','日本語を含むJSONを読みやすいインデント付きで出力し、末尾の改行とUTF-8のバイト列に変換します。','出力ファイルの保存とハッシュの計算で使われます。'],
  'LightweightDecisionBundleService._hash':['バイト列のSHA-256を計算する','入力されたバイト列のSHA-256を16進文字列で返します。','manifest に入力・出力ファイルの同一性を記録するために使われます。']
};
function readingNote(file,node){
  if(graph.meta.head==='WORKTREE'||graph.meta.base==='WORKTREE'||graph.meta.base_commit!==HISTORY_COMPARISON.base||graph.meta.head_commit!==HISTORY_COMPARISON.head)return null;
  const note=HISTORY_NOTES[file];if(!note)return null;
  const fn=node&&file===SERVICE&&FUNCTION_NOTES[node.qualname];
  return fn?{title:fn[0],lead:fn[1],behavior:fn[2],checks:note.checks,refs:[[node.qualname,node.line,node.end_line]]}:note;
}
