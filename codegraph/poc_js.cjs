// Acorn parses repository source; repository JavaScript is never executed.
const acorn=require('./poc_vendor/acorn.cjs');
const fs=require('node:fs');
function walk(n,fn,parent=null,key=''){if(!n||typeof n!=='object')return;if(Array.isArray(n)){n.forEach(x=>walk(x,fn,parent,key));return;}if(fn(n,parent,key)===false)return;for(const [k,v] of Object.entries(n))if(!['loc','start','end'].includes(k))walk(v,fn,n,k);}
function canonical(value,bindings={},parent=null,key=''){
 if(typeof value==='bigint')return String(value)+'n';
 if(value===null||typeof value!=='object')return value;
 if(Array.isArray(value))return value.map(x=>canonical(x,bindings,parent,key));
 const out={};for(const k of Object.keys(value).sort()){
  if(['loc','start','end','raw'].includes(k))continue;
  if(value.type==='Identifier'&&k==='name'&&bindings[value.name]&&!(parent?.type==='MemberExpression'&&key==='property'&&!parent.computed))out[k]=bindings[value.name];
  else out[k]=canonical(value[k],bindings,value,k);
 }return out;
}
function parse(file,text){
 const result={nodes:[],edges:[],units:[],warnings:[],unresolved:0,state:'partial'};
 let tree;try{tree=acorn.parse(text,{ecmaVersion:'latest',sourceType:file.endsWith('.cjs')?'script':'module',locations:true,allowHashBang:true});}catch(e){return {...result,state:'failed',warnings:[`${file}: ${e.message}`]};}
 const definitions=[];
 for(let statement of tree.body){if(statement.type==='ExportNamedDeclaration'||statement.type==='ExportDefaultDeclaration')statement=statement.declaration;if(!statement)continue;
  if(statement.type==='FunctionDeclaration'&&statement.id)definitions.push([statement.id.name,statement]);
  if(statement.type==='VariableDeclaration')for(const d of statement.declarations)if(d.id.type==='Identifier'&&['ArrowFunctionExpression','FunctionExpression'].includes(d.init?.type))definitions.push([d.id.name,d.init]);
 }
 const byName=new Map(definitions.map(([name,n])=>[name,{id:file+'::'+name,name,qualname:name,file,line:n.loc.start.line,end_line:n.loc.end.line,kind:'function',language:'JavaScript'}]));
 result.nodes=[...byName.values()];
 for(const [name,fn] of definitions){const node=byName.get(name),locals=new Set(),bindings={};let safe=true;
  for(const p of fn.params){if(p.type!=='Identifier')safe=false;else locals.add(p.name);}
  walk(fn.body,(n)=>{if(n!==fn.body&&/Function|Class/.test(n.type)){safe=false;return false;}if(['ObjectExpression','ObjectPattern','ArrayPattern','WithStatement','ImportExpression'].includes(n.type)||n.type==='BlockStatement'&&n!==fn.body)safe=false;if(n.type==='VariableDeclarator'){if(n.id.type==='Identifier')locals.add(n.id.name);else safe=false;}});
  let count=0;for(const local of locals)bindings[local]='$local'+count++;
  walk(fn.body,n=>{if(n!==fn.body&&/Function|Class/.test(n.type))return false;if(n.type!=='CallExpression'&&n.type!=='NewExpression')return;
   const target=n.callee.type==='Identifier'&&!locals.has(n.callee.name)?byName.get(n.callee.name):null;
   if(target)result.edges.push({source:node.id,target:target.id,file,line:n.loc.start.line,end_line:n.loc.end.line,text:text.slice(n.start,n.end)});else result.unresolved++;
  });
  const body=fn.body.type==='BlockStatement'?fn.body.body:[];
  const regions=[{body,tag:'whole'}];for(let i=0;i+3<=body.length;i++)if(body.length!==3)regions.push({body:body.slice(i,i+3),tag:'block'+i});
  for(const r of regions){if(r.body.length<3)continue;const start=r.body[0].start,end=r.body.at(-1).end;let tokens=0;try{const t=acorn.tokenizer(text.slice(start,end),{ecmaVersion:'latest'});while(t.getToken().type.label!=='eof')tokens++;}catch{continue;}if(tokens<20)continue;
   result.units.push({file,owner:name,tag:r.tag,start:r.body[0].loc.start.line,end:r.body.at(-1).loc.end.line,text:text.slice(start,end),type1:JSON.stringify(canonical(r.body)),type2:safe?JSON.stringify(canonical(r.body,bindings)):null,bindings,parameters:fn.params.filter(p=>p.type==='Identifier').map(p=>p.name),language:'JavaScript'});
  }
 }
 result.warnings.push(`${file}: トップレベルの関数宣言・変数に代入した関数のみ。import先・メソッド・ネスト関数は未解決／対象外。`);
 return result;
}
const files=JSON.parse(fs.readFileSync(0,'utf8'));const result={};for(const [file,text] of Object.entries(files))result[file]=parse(file,text);process.stdout.write(JSON.stringify(result));
