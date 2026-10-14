/* Repository content is rendered as text. Reading notes are bound to one exact comparison. */
let graph,cy,depth=2,busy=false,selectedId=null,selectedFile=null,mode='files',filter='changed';
let reviewed=new Set(),snapshotId=null,storageOK=true,resizeFrame,displayKey=null;
const $=id=>document.getElementById(id);
const add=(p,tag,text,cls)=>{const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;p.append(e);return e;};
const basename=path=>path.split('/').pop();
const shortRef=ref=>/^[a-f0-9]{40}$/i.test(ref)?ref.slice(0,7):ref;
function fileGraph(data){
  const files=new Map(),ids=new Map(),edges=new Map();
  for(const n of data.nodes){ids.set(n.id,n.file);if(!files.has(n.file))files.set(n.file,{id:'file:'+n.file,file:n.file,label:basename(n.file),count:0,changed:false,affected:false,deleted:true});const f=files.get(n.file);f.count++;f.changed||=n.changed;f.affected||=n.affected;f.deleted&&=n.deleted;}
  for(const e of data.edges){const source=ids.get(e.source),target=ids.get(e.target);if(!source||!target||source===target)continue;const key=JSON.stringify([source,target]);if(!edges.has(key))edges.set(key,{id:'file-edge:'+key,source:'file:'+source,target:'file:'+target,count:0,impact:false,deleted:true});const a=edges.get(key);a.count++;a.impact||=e.impact;a.deleted&&=e.deleted;}
  return {nodes:[...files.values()].map(n=>({...n,size:Math.min(66,22+Math.sqrt(n.count)*7)})),edges:[...edges.values()]};
}
function functionGraph(data,file){
  const local=new Set(data.nodes.filter(n=>n.file===file).map(n=>n.id)),visible=new Set(local);
  data.edges.forEach(e=>{if(local.has(e.source)||local.has(e.target)){visible.add(e.source);visible.add(e.target);}});
  return {nodes:data.nodes.filter(n=>visible.has(n.id)).map(n=>({...n,label:n.qualname==='<module>'?basename(n.file):n.name,size:n.changed?27:20})),edges:data.edges.filter(e=>visible.has(e.source)&&visible.has(e.target))};
}
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
function currentNode(){return graph.nodes.find(n=>n.id===selectedId);}
function nodesForFile(file){return graph.nodes.filter(n=>n.file===file);}
function selectFile(file){document.querySelector('.detail').scrollTop=0;selectedFile=file;selectedId=null;renderList();renderExplanation();renderCode();selectGraph();}
function selectNode(id){document.querySelector('.detail').scrollTop=0;const n=graph.nodes.find(n=>n.id===id);if(!n)return;selectedId=id;selectedFile=n.file;renderList();renderExplanation();renderCode();selectGraph();}
function selectGraph(){if(!cy)return;cy.nodes().unselect();cy.elements().removeClass('related');const node=cy.getElementById(mode==='files'?'file:'+selectedFile:selectedId||'');if(node.length){node.select();node.closedNeighborhood().addClass('related');} updateLabels();}
function status(nodes){return nodes.some(n=>n.changed)?'変更':nodes.some(n=>n.affected)?'影響候補':'通常';}
function renderList(){
  const query=$('search').value.trim().toLowerCase(),model=fileGraph(graph),panel=$('fileList');panel.replaceChildren();
  const files=model.nodes.filter(f=>(filter==='all'||f.changed||f.affected)&&(!query||f.file.toLowerCase().includes(query)||nodesForFile(f.file).some(n=>n.qualname.toLowerCase().includes(query)))).sort((a,b)=>Number(b.changed)-Number(a.changed)||Number(b.affected)-Number(a.affected)||a.file.localeCompare(b.file));
  if(!files.length)add(panel,'p','一致する対象がありません。','file-meta');
  for(const f of files){const b=add(panel,'button','','file-row'+(f.file===selectedFile?' selected':''));b.setAttribute('aria-label',f.file+' を読む');add(b,'span',status(nodesForFile(f.file)),'state');add(b,'span',basename(f.file),'file-title');add(b,'span',f.file.replace(/\/[^/]+$/,''),'file-meta');const delta=graph.changed_files.find(c=>c.file===f.file);add(b,'span',`${f.count} 定義${delta?` · +${delta.added} / −${delta.removed}`:''}`,'file-meta');b.onclick=()=>{if(mode==='functions'){selectedFile=f.file;selectedId=null;drawGraph();}selectFile(f.file);};}
  const defs=$('definitions');defs.replaceChildren();if(!selectedFile)return;add(defs,'div','このファイルの定義','section-label');
  for(const n of nodesForFile(selectedFile)){if(n.kind==='module')continue;if(query&&!`${n.qualname} ${n.file}`.toLowerCase().includes(query))continue;const row=add(defs,'div','','definition-row');const check=document.createElement('input');check.type='checkbox';check.checked=reviewed.has(n.id);check.disabled=!n.changed&&!n.affected;check.setAttribute('aria-label',n.qualname+'を確認済みにする');check.onchange=()=>markReviewed(n.id,check.checked);row.append(check);const b=add(row,'button',n.qualname+(n.changed?' · 変更':n.affected?' · 影響':''),n.id===selectedId?'selected':'');b.onclick=()=>{selectNode(n.id);if(mode!=='functions'){mode='functions';drawGraph();}showPanel('explain');};}
}
function evidenceButton(parent,file,line,label){const node=nodesForFile(file).find(n=>n.line===line)||nodesForFile(file).find(n=>n.line<=line&&n.end_line>=line);const b=add(parent,'button',`${label} · L${line}`,'link-node');b.onclick=()=>{if(node)selectNode(node.id);showPanel('code');document.querySelector('.detail').scrollTop=0;};}
function renderExplanation(){
  const panel=$('explanation');panel.replaceChildren();if(!selectedFile){add(panel,'h2','ファイルを選んでください');return;}
  const node=currentNode(),nodes=nodesForFile(selectedFile),note=readingNote(selectedFile,node);add(panel,'div',status(node?[node]:nodes),'badge');
  add(panel,'h2',note?note.title:node?node.qualname:basename(selectedFile));
  add(panel,'div',selectedFile+(node?`\nL${node.line}–${node.end_line}`:''),'node-path');
  if(note){add(panel,'p',note.lead,'lead');add(panel,'h3','何をするコードか');add(panel,'p',note.behavior);add(panel,'h3','読むときの確認点');add(panel,'p',note.checks);add(panel,'h3','説明の根拠');note.refs.forEach(([name,line,end])=>{evidenceButton(panel,selectedFile,line,`${name}（L${line}–${end}）`);});add(panel,'p','この比較のソースを確認して作成した読解メモ。別の比較では表示しません。','provenance');}
  else{const delta=graph.changed_files.find(f=>f.file===selectedFile);const label=node?`${node.kind} ${node.qualname}`:`${nodes.length}個の定義を含むPythonファイル`;add(panel,'p',`${label}です。${node&&node.deleted?'比較先では削除されています。':delta?delta.status==='added'?'この比較でファイルが追加されました。':`このファイルには追加${delta.added}行・削除${delta.removed}行の差分があります。`:'このファイルに直接の差分はありません。'}`,'lead');add(panel,'h3','確認できる関係');const outgoing=graph.edges.filter(e=>node?e.source===node.id:nodes.some(n=>n.id===e.source)),incoming=graph.edges.filter(e=>node?e.target===node.id:nodes.some(n=>n.id===e.target));add(panel,'p',`解決済みの呼び出しは、呼ぶ側として${outgoing.length}箇所、呼ばれる側として${incoming.length}箇所です。詳しい行は「コード・根拠」で確認できます。`);add(panel,'p','この対象の振る舞いを説明する読解メモはまだありません。変更の意図はコードの構造だけでは判断できません。','provenance');}
  if(node&&(node.changed||node.affected)){const l=add(panel,'label','','review-check');const c=document.createElement('input');c.type='checkbox';c.checked=reviewed.has(node.id);c.onchange=()=>markReviewed(node.id,c.checked);l.append(c);add(l,'span','この定義を確認済みにする');}
  add(panel,'h3','関数を読む');const defs=nodes.filter(n=>n.kind!=='module');for(const n of defs.slice(0,14)){const b=add(panel,'button',n.qualname,'link-node');b.onclick=()=>{selectNode(n.id);mode='functions';drawGraph();document.querySelector('.detail').scrollTop=0;};}if(defs.length>14)add(panel,'p','残りの定義は左側の一覧から選べます。');
}
function renderCode(){
  const p=$('inspector');p.replaceChildren();const n=currentNode();if(!selectedFile)return;add(p,'h2',n?n.qualname:basename(selectedFile));add(p,'div',selectedFile,'node-path');
  const changes=n?n.changes:graph.changed_files.filter(f=>f.file===selectedFile);add(p,'h3','変更差分');if(!changes.length)add(p,'p','直接の変更はありません。');for(const c of changes){const d=add(p,'details','');add(d,'summary',n?`差分 · Base L${c.old_start} → Head L${c.start}`:`ファイル差分 · +${c.added} / −${c.removed}`);add(d,'pre',c.patch||'表示できる差分がありません。','source-code');}
  if(n){for(const [title,src] of [['Base のコード',n.before],['Head のコード',n.after]]){const d=add(p,'details','');add(d,'summary',title);if(src){add(d,'pre',src.text.split('\n').map((t,i)=>`${src.line+i}  ${t}`).join('\n'),'source-code');if(src.truncated)add(d,'p','120行まで表示しています。');}else add(d,'p','このスナップショットに定義はありません。');}if(n.evidence_path.length){add(p,'h3','変更へ至る根拠経路');for(const id of n.evidence_path){const e=graph.edges.find(e=>e.id===id);add(p,'div',`${e.file}:${e.line}\n${e.text}`,'evidence');}}}
  const ids=new Set((n?[n]:nodesForFile(selectedFile)).map(n=>n.id));for(const [title,field,other] of [['呼び出し元','target','source'],['呼び出し先','source','target']]){add(p,'h3',title);const edges=graph.edges.filter(e=>ids.has(e[field]));if(!edges.length)add(p,'p','解析で解決された呼び出しはありません。');for(const e of edges.slice(0,80)){const t=graph.nodes.find(n=>n.id===e[other]);const b=add(p,'button',t.qualname,'link-node');b.onclick=()=>{selectNode(t.id);mode='functions';drawGraph();showPanel('code');};add(p,'div',`${e.deleted?'[Base] ':''}${e.file}:${e.line}\n${e.text}`,'evidence');}if(edges.length>80)add(p,'p','先頭80箇所を表示しています。');}
  const findings=graph.review.findings.filter(f=>f.file===selectedFile);if(findings.length){add(p,'h3','静的チェック');findings.forEach(f=>{add(p,'div',`${f.code} · ${f.file}:${f.line}\n${f.message}\n${f.suggestion}`,'finding');});}
}
function drawGraph(){
  const key=graph.meta.snapshot_id+':'+mode+(mode==='functions'?':'+selectedFile:'');const preserve=cy&&displayKey===key;const positions=new Map();if(preserve)cy.nodes().forEach(n=>positions.set(n.id(),n.position()));const oldZoom=preserve?cy.zoom():null,oldPan=preserve?cy.pan():null;
  if(cy)cy.destroy();const model=mode==='files'?fileGraph(graph):functionGraph(graph,selectedFile);
  cy=cytoscape({container:$('cy'),elements:[...model.nodes.map(({parent,...n})=>({data:{...n,label:n.label.replace(/\.py$/,'')},position:positions.get(n.id),classes:[n.changed?'changed':'',n.affected?'affected':'',n.deleted?'deleted':''].join(' ')})),...model.edges.map(e=>({data:e,classes:(e.impact?'impact ':'')+(e.deleted?'deleted':'')}))],style:[
    {selector:'node',style:{'width':'data(size)','height':'data(size)','background-color':'#73a3a3','background-opacity':.76,'label':'','font-size':11,'color':'#325c68','text-valign':'bottom','text-margin-y':5,'text-wrap':'ellipsis','text-max-width':105,'min-zoomed-font-size':7,'text-outline-width':2,'text-outline-color':'#fbfdfc'}},
    {selector:'edge',style:{'width':1,'line-color':'#cbd8d8','target-arrow-color':'#a4bdbd','target-arrow-shape':'triangle','arrow-scale':.6,'curve-style':'bezier','opacity':.65}},
    {selector:'node.changed',style:{'background-color':'#49bf88','background-opacity':.95,'border-width':2,'border-color':'#37966e'}},
    {selector:'node.affected',style:{'background-color':'#f0f5f4','border-width':2,'border-color':'#779b98'}},
    {selector:'edge.impact',style:{'line-color':'#6f9d8e','target-arrow-color':'#6f9d8e','width':2,'opacity':1}},
    {selector:'.deleted',style:{'line-style':'dashed','border-style':'dashed','border-width':2,'border-color':'#95aaa8'}},
    {selector:'edge.related',style:{'line-color':'#679790','target-arrow-color':'#679790','width':1.7,'opacity':1}},
    {selector:'node:selected',style:{'border-width':4,'border-color':'#816a98','color':'#583f70','font-weight':'bold','z-index':10,'text-max-width':170}},
    {selector:'node.labeled',style:{'label':'data(label)'}},
    {selector:'node.hover',style:{'label':'data(label)','border-width':3,'border-color':'#729b91','text-max-width':180,'z-index':9}}
  ],layout:preserve?{name:'preset',fit:false}:{name:'cose',animate:false,randomize:false,nodeRepulsion:()=>mode==='files'?19000:14000,idealEdgeLength:()=>110,componentSpacing:90,padding:35},minZoom:.06,maxZoom:3,wheelSensitivity:.2});
  cy.on('zoom pan',updateLabels);
  cy.on('tap','node',e=>{if(mode==='files')selectFile(e.target.data('file'));else selectNode(e.target.id());showPanel('explain');document.querySelector('.detail').scrollTop=0;});cy.on('mouseover','node',e=>e.target.addClass('hover'));cy.on('mouseout','node',e=>e.target.removeClass('hover'));
  $('modeFiles').classList.toggle('active',mode==='files');$('modeFunctions').classList.toggle('active',mode==='functions');$('modeFunctions').disabled=!selectedFile;$('graphScope').textContent=mode==='files'?`${model.nodes.length} FILES · CODEBASE MAP`:basename(selectedFile)+' · 関数と隣接する定義';$('summary').textContent=`${shortRef(graph.meta.base)} → ${shortRef(graph.meta.head)} · ${graph.meta.changed} 変更定義 · ${graph.meta.affected} 影響候補`;$('summary').title=`${graph.meta.base} → ${graph.meta.head}`;document.querySelector('.graph-note').textContent=mode==='files'?'矢印は呼び出す側 → 呼ばれる側。円の大きさは定義数。':'選択ファイルの定義と、直接つながる定義を表示。';selectGraph();if(preserve){cy.zoom(oldZoom);cy.pan(oldPan);updateLabels();}else fit();displayKey=key;
}
function updateLabels(){
  if(!cy)return;const zoom=cy.zoom(),placed=[];
  cy.style().selector('node').style({'font-size':9/zoom,'text-max-width':105/zoom,'text-outline-width':1/zoom,'min-zoomed-font-size':0}).update();
  cy.nodes().removeClass('labeled');
  const nodes=cy.nodes().toArray().sort((a,b)=>(Number(b.selected())*1000+Number(b.hasClass('changed'))*100+Number(b.hasClass('affected'))*50+b.degree())-(Number(a.selected())*1000+Number(a.hasClass('changed'))*100+Number(a.hasClass('affected'))*50+a.degree()));
  for(const n of nodes){const p=n.renderedPosition(),width=Math.min(105,String(n.data('label')).length*5.5),top=p.y+n.data('size')*zoom/2+5;
    const rect={left:p.x-width/2,right:p.x+width/2,top,bottom:top+13};
    const important=n.selected()||n.hasClass('changed')||n.hasClass('affected');
    if(important||!placed.some(r=>rect.left<r.right+5&&rect.right>r.left-5&&rect.top<r.bottom+3&&rect.bottom>r.top-3)){n.addClass('labeled');placed.push(rect);}
  }
}
function fit(){if(!cy)return;cy.resize();cy.fit(undefined,60);updateLabels();}
function showPanel(panel){$('explanation').hidden=panel!=='explain';$('inspector').hidden=panel!=='code';$('tabExplain').classList.toggle('active',panel==='explain');$('tabCode').classList.toggle('active',panel==='code');}
function loadReviewed(){if(snapshotId===graph.meta.snapshot_id)return;snapshotId=graph.meta.snapshot_id;reviewed=new Set();storageOK=true;try{const ids=JSON.parse(localStorage.getItem('plism-review:'+snapshotId)||'[]');if(Array.isArray(ids))reviewed=new Set(ids.filter(x=>typeof x==='string'));}catch(e){storageOK=false;}}
function updateProgress(){const ids=graph.review.reading_order;$('progress').textContent=`${ids.filter(id=>reviewed.has(id)).length} / ${ids.length} 定義を確認済み`;$('storageStatus').textContent=storageOK?'確認記録はこのブラウザに保存されます。':'確認記録はこのページを開いている間だけ保持されます。';}
function markReviewed(id,yes){if(yes)reviewed.add(id);else reviewed.delete(id);try{localStorage.setItem('plism-review:'+snapshotId,JSON.stringify([...reviewed]));}catch(e){storageOK=false;}updateProgress();renderList();}
async function load(refresh=false){
  if(busy)return;busy=true;['refresh','depth1','depth2'].forEach(id=>$(id).disabled=true);
  try{const q=new URLSearchParams();if(graph)q.set('depth',depth);if($('base').value)q.set('base',$('base').value);if($('head').value)q.set('head',$('head').value);if(refresh)q.set('refresh','1');const r=await fetch('/api/graph?'+q);const data=await r.json();if(!r.ok)throw Error(data.error);const newSnapshot=!graph||graph.meta.snapshot_id!==data.meta.snapshot_id;graph=data;depth=data.meta.depth;loadReviewed();if(newSnapshot){selectedId=null;selectedFile=nodesForFile(SERVICE).length?SERVICE:graph.changed_files[0]?.file||graph.nodes[0]?.file;mode='files';}if(!nodesForFile(selectedFile).length){selectedFile=graph.nodes[0]?.file;selectedId=null;}if(selectedId&&!currentNode())selectedId=null;$('base').value=graph.meta.base;$('head').value=graph.meta.head;$('repoName').textContent=graph.meta.repo.split(/[\\/]/).pop()+' / 変更の理解';$('warnings').textContent=[`対象: ${graph.meta.repo}`,`Base: ${graph.meta.base_commit}`,`Head: ${graph.meta.head_commit}`,`未解決呼び出し: ${graph.meta.unresolved_calls}`,...graph.warnings].join('\n');$('warningCount').textContent=`解析の範囲と限界 · 未解決 ${graph.meta.unresolved_calls} 件`;$('message').textContent=graph.nodes.length?'':'Pythonの定義がありません。';updateProgress();renderList();renderExplanation();renderCode();drawGraph();}
  catch(e){$('message').textContent=`解析できませんでした: ${e.message}${graph?'（前回の結果を表示）':''}`;if(graph)depth=graph.meta.depth;}
  finally{busy=false;['refresh','depth1','depth2'].forEach(id=>$(id).disabled=false);$('depth1').classList.toggle('active',depth===1);$('depth2').classList.toggle('active',depth===2);}
}
function reportText(){const m=graph.meta,lines=['# PLISM Change Review','',`Repository: ${m.repo}`,`Base: ${m.base} (${m.base_commit})`,`Head: ${m.head} (${m.head_commit})`,`Impact depth: ${m.depth}`,'','静的解析による候補です。確認記録は安全性の保証ではありません。','','## 変更ファイル',''];for(const f of graph.changed_files){lines.push(`- ${f.file}: +${f.added} / -${f.removed}`);const note=readingNote(f.file);if(note)lines.push('',`### ${note.title}`,note.lead,note.behavior,note.checks,'');}lines.push('','## 確認する定義','');for(const id of graph.review.reading_order){const n=graph.nodes.find(n=>n.id===id);lines.push(`- [${reviewed.has(id)?'x':' '}] ${n.qualname} — ${n.file}:${n.line}`);for(const edgeId of n.evidence_path){const e=graph.edges.find(e=>e.id===edgeId);lines.push(`  - ${e.file}:${e.line} ${e.text.replaceAll('\n',' ')}${e.deleted?' [Base]':''}`);}}lines.push('','## 静的チェック','');for(const f of graph.review.findings)lines.push(`- ${f.code} — ${f.file}:${f.line}: ${f.message}`);lines.push('','## 解析の限界','',`未解決call: ${m.unresolved_calls}`,...graph.warnings);return lines.join('\n')+'\n';}
$('search').oninput=renderList;$('refresh').onclick=()=>load(true);for(const d of [1,2])$('depth'+d).onclick=()=>{depth=d;load();};
for(const [id,value] of [['filterChanged','changed'],['filterAll','all']])$(id).onclick=()=>{filter=value;$('filterChanged').classList.toggle('active',filter==='changed');$('filterAll').classList.toggle('active',filter==='all');renderList();};
$('modeFiles').onclick=()=>{mode='files';drawGraph();};$('modeFunctions').onclick=()=>{mode='functions';drawGraph();};$('tabExplain').onclick=()=>showPanel('explain');$('tabCode').onclick=()=>showPanel('code');$('fit').onclick=fit;$('zoomIn').onclick=()=>cy&&cy.zoom(cy.zoom()*1.25);$('zoomOut').onclick=()=>cy&&cy.zoom(cy.zoom()/1.25);
$('downloadReport').onclick=()=>{if(!graph)return;const url=URL.createObjectURL(new Blob([reportText()],{type:'text/markdown;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='plism-review-'+snapshotId.slice(0,12)+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(fit);}).observe($('cy'));
if(typeof cytoscape==='undefined')$('message').textContent='Cytoscape.js が見つかりません。';else load();
