const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const {webcrypto,createHash}=require('node:crypto');
const code=fs.readFileSync('web/workbench.js','utf8');const part=code.slice(code.indexOf('async function digest('),code.indexOf('function replayRender('));
function makeContext(){const c={crypto:webcrypto,TextEncoder,Uint8Array,URL};vm.createContext(c);vm.runInContext(part,c);return c}
const original=fs.readFileSync('web/replays/fastapi-python311.json','utf8');
function repack(payload){const payload_json=JSON.stringify(payload);return JSON.stringify({schema_version:'1.0',payload_json,sha256:createHash('sha256').update(payload_json).digest('hex')})}
test('actual recorded replay passes browser integrity and citation checks',async()=>{const p=await makeContext().validateReplay(original);assert.equal(p.session.reports[0].repositories[0].rows[0].status,'PASS')});
test('tampering and foreign source or citation are rejected',async()=>{const c=makeContext();const b=JSON.parse(original);b.payload_json+=' ';await assert.rejects(c.validateReplay(JSON.stringify(b)));let p=JSON.parse(JSON.parse(original).payload_json);Object.values(p.evidence)[0].source_url='https://github.com/other/repo';await assert.rejects(c.validateReplay(repack(p)));p=JSON.parse(JSON.parse(original).payload_json);p.session.reports[0].repositories[0].rows[0].citations[0].evidence_id='ev_foreign';await assert.rejects(c.validateReplay(repack(p)));p=JSON.parse(JSON.parse(original).payload_json);const e=Object.values(p.evidence).find(e=>e.source_type==='file_lines');e.source_url=e.source_url.replace(e.commit,'0'.repeat(40));await assert.rejects(c.validateReplay(repack(p)))});

function uiContext(){
  const elements=new Map();
  function node(){return {hidden:false,disabled:false,dataset:{},children:[],classList:{toggle(){}},replaceChildren(...x){this.children=x},append(...x){this.children.push(...x)},addEventListener(type,fn){(this.listeners??={})[type]??=[];this.listeners[type].push(fn)},set textContent(v){this.text=String(v)},get textContent(){return this.text||''}}}
  const brand=node();const document={getElementById(id){if(!elements.has(id))elements.set(id,node());return elements.get(id)},createElement:node,querySelector(){return brand},querySelectorAll(){return []}};
  const streams=[];class FakeEventSource{constructor(){this.handlers={};streams.push(this)}addEventListener(k,fn){this.handlers[k]=fn}close(){this.closed=true}emit(k){this.handlers[k]?.()}}
  const callbacks=[];const context={document,window:{scrollTo(){}},EventSource:FakeEventSource,setInterval(fn){callbacks.push(fn);return callbacks.length},clearInterval(){},localStorage:{setItem(){}}};
  vm.createContext(context);vm.runInContext(code.slice(0,code.indexOf('async function digest(')),context);
  return {context,document,brand,streams,callbacks};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}};
test('navigation registers the brand listener once regardless of view switches',()=>{
  const {context,brand}=uiContext();const line=code.split('\n').find(line=>line.startsWith("document.querySelector('.brand').addEventListener"));vm.runInContext(line,context);
  for(let i=0;i<5;i++)context.view(i%2?'discover':'audit');assert.equal(brand.listeners.click.length,1);
});
test('terminal event queues a final fetch after a pending refresh and renders result',async()=>{
  const {context,streams}=uiContext();const first=deferred(),last=deferred(),queue=[first,last],seen=[];
  context.apiMock=()=>queue.shift().promise;context.renderMock=s=>seen.push(s.status);context.historyMock=()=>{};
  vm.runInContext('api=apiMock;render=renderMock;history=historyMock;subscribeSession("one",0)',context);
  streams[0].emit('update');streams[0].emit('terminal');first.resolve({status:'INVESTIGATING'});await flush();
  assert.deepEqual(seen,['INVESTIGATING']);last.resolve({status:'COMPLETED',reports:[{result:'done'}]});await flush();
  assert.deepEqual(seen,['INVESTIGATING','COMPLETED']);assert.equal(vm.runInContext('w.stream',context),null);
});
test('late stream responses cannot overwrite a different session',async()=>{
  const {context,streams}=uiContext();const first=deferred(),seen=[];context.apiMock=()=>first.promise;context.renderMock=s=>seen.push(s.id);context.historyMock=()=>{};
  vm.runInContext('api=apiMock;render=renderMock;history=historyMock;subscribeSession("old",0)',context);streams[0].emit('update');streams[0].emit('terminal');
  vm.runInContext('stopStream();subscribeSession("new",0)',context);first.resolve({id:'old',status:'COMPLETED'});await flush();assert.deepEqual(seen,[]);assert.equal(streams[0].closed,true);
});
test('tool arguments display bounded JSON as text and stale leases expose recovery',()=>{
  const {context,document}=uiContext();context.timeline([{id:1,type:'tool_requested',data:{repo:'a/b',tool:'read',args:{path:'<script>x</script>',start_line:1}}},{id:2,type:'tool_requested',data:{repo:'a/b',tool:'read',args:{query:'x'.repeat(1000)}}}]);
  const entries=document.getElementById('timeline').children;assert.match(entries[0].children[1].textContent,/"path":"<script>x<\/script>"/);assert.match(entries[1].children[1].textContent,/已截断/);assert.ok(entries[1].children[1].textContent.length<560);
  vm.runInContext('w.modelReady=true;w.session={id:"one",status:"INVESTIGATING",lease_busy:true};updateControls()',context);assert.equal(document.getElementById('resume').hidden,true);
  vm.runInContext('w.session.lease_busy=false;updateControls()',context);assert.equal(document.getElementById('resume').hidden,false);assert.match(document.getElementById('actionStatus').textContent,/没有有效执行权/);
});
test('report selector shows earlier live turns and gates replay turns by report_ready',()=>{
  const {context,document}=uiContext();const seen=[];context.matrixMock=report=>seen.push(report?.query||null);
  vm.runInContext('matrix=matrixMock',context);
  const listener=code.split('\n').find(line=>line.startsWith("$('reportSelect').addEventListener"));vm.runInContext(listener,context);
  const s={id:'two-turns',status:'COMPLETED',bindings:[],usage:{},events:[{id:1,type:'report_ready',data:{version:1}},{id:2,type:'report_ready',data:{version:2}}],reports:[{query:'首轮 Python 3.10'},{query:'追问 Python 3.11'}]};
  context.render(s);assert.equal(seen.at(-1),'追问 Python 3.11');assert.equal(document.getElementById('reportSelect').children.length,2);
  document.getElementById('reportSelect').listeners.change[0]({target:{value:'0'}});assert.equal(seen.at(-1),'首轮 Python 3.10');assert.equal(document.getElementById('sessionTitle').textContent,'首轮 Python 3.10');
  vm.runInContext('w.replay={}',context);context.render(s,[]);assert.equal(seen.at(-1),null);assert.equal(document.getElementById('reportPicker').hidden,true);
  context.render(s,[s.events[0]]);assert.equal(seen.at(-1),'首轮 Python 3.10');assert.equal(document.getElementById('reportSelect').children.length,1);
  document.getElementById('reportSelect').listeners.change[0]({target:{value:'1'}});assert.equal(seen.at(-1),'首轮 Python 3.10');
  context.render(s,s.events);assert.equal(seen.at(-1),'追问 Python 3.11');assert.equal(document.getElementById('reportSelect').children.length,2);
  document.getElementById('reportSelect').listeners.change[0]({target:{value:'0'}});assert.equal(seen.at(-1),'首轮 Python 3.10');
});
test('derived replay identities and their underlying source ranges are verified',async()=>{
  const c=makeContext(),payload=JSON.parse(JSON.parse(original).payload_json);
  const base=Object.values(payload.evidence).find(e=>e.source_type==='file_lines');
  const entry={path:base.path,evidence_id:base.evidence_id,start_line:base.start_line,end_line:base.end_line,category:'entry_or_route'};
  const body={rule_version:'arch-v1',scope:{path_prefix:'',files:[base.path]},references:[base.evidence_id],edges:[entry]};
  const item={source_type:'arch_profile',repo:base.repo,commit:base.commit,path_prefix:'',rule_version:'arch-v1',references:[base.evidence_id],text:JSON.stringify(body),source_url:`https://github.com/${base.repo}/tree/${base.commit}`,fetched_at:base.fetched_at};
  item.artifact_sha256=await c.digest(item.text);item.evidence_id=await c.evidenceId(item);payload.evidence[item.evidence_id]=item;
  await c.validateReplay(repack(payload));
  const badBody=JSON.parse(item.text);badBody.edges[0].start_line=base.end_line+1;item.text=JSON.stringify(badBody);item.artifact_sha256=await c.digest(item.text);delete payload.evidence[item.evidence_id];item.evidence_id=await c.evidenceId(item);payload.evidence[item.evidence_id]=item;
  await assert.rejects(c.validateReplay(repack(payload)));
});
test('all three v2 recordings still validate unchanged in the v3 browser',async()=>{
  const c=makeContext();for(const name of ['agents-python-comparison.json','fastapi-python311.json','pydantic-model-endpoint.json']){const raw=fs.readFileSync('web/replays/'+name,'utf8');const payload=await c.validateReplay(raw);assert.ok(payload.session.id)}
});
