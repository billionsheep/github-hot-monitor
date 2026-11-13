const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
test('spotlight displays each leaderboard score including zero', () => {
  const cards = [], grid = {innerHTML:'', appendChild(card) { cards.push(card); }};
  const document = {getElementById:() => grid, createElement:() => ({})};
  const context = {document}; vm.createContext(context);
  vm.runInContext(fs.readFileSync('web/app.js','utf8').replace(/main\(\);\s*$/, ''), context);
  const row = {full_name:'a/b',url:'https://github.com/a/b',stars:4,total:99,velocity:7,interesting:0,advanced:25,productive:30};
  context.renderSpotlight({leaderboards:Object.fromEntries(['fastest','interesting','advanced','productive','overall'].map(k => [k,[row]]))});
  for (const [i,value] of ['7.00 stars/day','Score 0.00','Score 25.00','Score 30.00','Score 99.00'].entries()) assert.ok(cards[i].innerHTML.includes(value));
});
const flush = () => new Promise(resolve => setImmediate(resolve));
function node(tag='div') {
  let content = '';
  return {tag, children:[], dataset:{}, disabled:false, hidden:false, attributes:{}, className:'',
    classList:{add(){}}, set textContent(v) {content=v; this.children=[];}, get textContent() {return content;},
    setAttribute(k,v) {this.attributes[k]=v;}, append(...c) {this.children.push(...c);},
    replaceChildren(...c) {content=''; this.children=c;}, addEventListener(type,fn) {this[type]=fn;} };
}
function response(data, status=200, type='application/json') {
  return {ok:status>=200 && status<300,status,headers:{get:() => type},json:async () => data};
}
const idsList=['evidenceForm','evidenceStatus','evidenceWorkspace','fileTree','evidenceCard','repositoryInput','snapshotInfo','treeStatus','shortcuts','createSnapshot','breadcrumbs'];
async function harness(fetch) {
  const ids=Object.fromEntries(idsList.map(id => [id,node()])); ids.createSnapshot.disabled=true; ids.repositoryInput.value='test/repo';
  const document={getElementById:id=>ids[id],createElement:tag=>node(tag)};
  const context={document,fetch,encodeURIComponent,navigator:{clipboard:{writeText:async()=>{}}}};
  vm.createContext(context); vm.runInContext(fs.readFileSync('web/evidence.js','utf8'),context); await flush();
  return ids;
}
const snapshot=id => ({id,repo:`test/${id}`,sha:'a'.repeat(40),created_at:'now'});
const tree=(names) => ({entries:names.map(name=>({name,type:'blob'})),truncated:false});
function fragment(path,start=1,options={}) {
  return {path,repository:'test/A',commit:'a',start_line:start,end_line:start,text:'<script>unsafe()</script>\n',empty:false,truncated:false,partial_line:false,fetched_at:'now',content_sha256:'f'.repeat(64),fragment_sha256:'e'.repeat(64),evidence_id:'ev_'+ '1'.repeat(64),source_url:'https://github.com/test/A/blob/a/file#L1', ...options};
}
const submit = ids => ids.evidenceForm.submit({preventDefault(){}});
const find = (root, text) => { if (root.textContent===text) return root; for (const c of root.children||[]) { const v=find(c,text); if(v) return v; } };
test('A to B tree failure clears A and retry is bound to B', async () => {
  let n=0, calls=[];
  const ids=await harness(async url=>{
    calls.push(url); if(url==='/api/capabilities') return response({service:'github-hot-monitor-evidence'});
    if(url==='/api/snapshots') return response(snapshot(++n===1?'A':'B'));
    if(url.includes('/A/tree')) return response(tree(['a.txt']));
    if(url.includes('/B/tree')) return response({detail:{message:'tree failed'}},502);
    return response(fragment('a.txt'));
  });
  await submit(ids); const stale=ids.fileTree.children[0]; assert.ok(stale);
  await submit(ids); assert.equal(ids.fileTree.children.length,0); assert.match(ids.treeStatus.children[0].textContent,/tree failed/);
  stale.click(); await flush(); assert.ok(!calls.some(x=>x.includes('/B/fragment')));
  find(ids.treeStatus,'重试目录').click(); await flush(); assert.equal(calls.filter(x=>x.includes('/B/tree')).length,2);
});
test('late A response cannot overwrite B', async () => {
  let n=0, resolveA;
  const ids=await harness(async url=>{
    if(url==='/api/capabilities') return response({service:'github-hot-monitor-evidence'});
    if(url==='/api/snapshots') return response(snapshot(++n===1?'A':'B'));
    if(url.includes('/A/tree')) return response(tree(['a.txt']));
    if(url.includes('/B/tree')) return response(tree(['b.txt']));
    if(url.includes('/A/fragment')) return new Promise(resolve=>{resolveA=resolve;});
    return response(fragment('b.txt'));
  });
  await submit(ids); ids.fileTree.children[0].click(); await submit(ids); ids.fileTree.children[0].click(); await flush();
  resolveA(response(fragment('a.txt'))); await flush(); assert.equal(ids.evidenceCard.children[0].textContent,'b.txt');
});
test('static and non-JSON responses disable submission with useful message', async () => {
  const ids=await harness(async()=>response(null,501,'text/html'));
  assert.equal(ids.createSnapshot.disabled,true); assert.match(ids.evidenceStatus.textContent,/静态榜单/);
  let calls=0; const live=await harness(async url=>{if(url==='/api/capabilities') return response({service:'github-hot-monitor-evidence'}); calls++; return response(null,501,'text/html');});
  await submit(live); assert.equal(calls,1); assert.match(live.evidenceStatus.textContent,/非 JSON.*501/);
});
test('line numbers, safe HTML and history-based navigation', async () => {
  const calls=[];
  const ids=await harness(async url=>{
    calls.push(url); if(url==='/api/capabilities') return response({service:'github-hot-monitor-evidence'});
    if(url==='/api/snapshots') return response(snapshot('A'));
    if(url.includes('/tree')) return response(tree(['file.txt']));
    return response(url.includes('start=2') ? fragment('file.txt',2) : fragment('file.txt',1,{truncated:true}));
  });
  await submit(ids); ids.fileTree.children[0].click(); await flush();
  let pre=find(ids.evidenceCard,'展开原文').children;
  const details=ids.evidenceCard.children.find(x=>x.tag==='details');
  const firstLine=details.children[1].children[0];
  assert.equal(firstLine.children[0].textContent,'1'); assert.equal(firstLine.children[1].textContent,'<script>unsafe()</script>');
  assert.equal(firstLine.children[1].children.length,0);
  find(ids.evidenceCard,'下一段').click(); await flush(); assert.ok(calls.some(x=>x.includes('start=2')));
  find(ids.evidenceCard,'上一段').click(); assert.ok(find(ids.evidenceCard,'原始行 1–1'));
  find(ids.evidenceCard,'下一段').click(); assert.ok(find(ids.evidenceCard,'原始行 2–2'));
  assert.equal(calls.filter(x=>x.includes('start=2')).length,1);
});
test('empty file displays no inverted range', async () => {
  const ids=await harness(async url=> url==='/api/capabilities' ? response({service:'github-hot-monitor-evidence'}) : url==='/api/snapshots' ? response(snapshot('A')) : url.includes('/tree') ? response(tree(['empty'])) : response(fragment('empty',1,{empty:true,start_line:null,end_line:null,text:''})));
  await submit(ids); ids.fileTree.children[0].click(); await flush(); assert.ok(find(ids.evidenceCard,'空文件（没有原始行）'));
});
