"""Transactional state transitions and lease ownership for Phase 2."""
import hashlib
import json
import time
import uuid
from evidence.github_client import timestamp

class Conflict(Exception): pass

def pack(data): return json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))

class HarnessStore:
    def __init__(self,db): self.db=db
    def create(self,bindings,query,key=None,budget=None):
        request_hash=hashlib.sha256(pack({'bindings':bindings,'query':query,'budget':budget}).encode()).hexdigest()
        with self.db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if key:
                existing=conn.execute('SELECT * FROM harness_keys WHERE key=?',(key,)).fetchone()
                if existing:
                    if existing['request_hash']!=request_hash: raise Conflict('幂等键已用于不同请求。')
                    return existing['session_id']
            id=uuid.uuid4().hex; turn=uuid.uuid4().hex; now=timestamp()
            state={'bindings':bindings,'query':query,'budget':budget,'criteria':[], 'repo_index':0,'summaries':[], 'history':[],
                   'context_id':uuid.uuid4().hex,'ranges':{},'outlines':[],'visible_evidence':[], 'lead_calls':0,'sub_calls':{},'tool_counts':{},
                   'report_version':0,'usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0},'turn_usage':{'input_tokens':0,'output_tokens':0,'total_tokens':0},'turn_model_calls':0,'turn_tool_calls':0,'reserved_input':0,'reserved_output':0,'unknown_calls':0}
            conn.execute('INSERT INTO audit_sessions(id,status,revision,turn_id,created_at,updated_at,payload) VALUES (?,?,?,?,?,?,?)',(id,'INIT',0,turn,now,now,pack(state)))
            if key: conn.execute('INSERT INTO harness_keys VALUES (?,?,?)',(key,id,request_hash))
            self._event(conn,id,turn,'created',{'status':'INIT'})
        return id
    def _event(self,conn,id,turn,kind,payload):
        seq=conn.execute('SELECT COALESCE(MAX(event_seq),0)+1 FROM audit_events WHERE session_id=?',(id,)).fetchone()[0]
        conn.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?)',(id,seq,turn,kind,timestamp(),pack(payload)))
    def acquire(self,id,owner,ttl=180):
        now=time.time()
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE'); row=c.execute('SELECT * FROM audit_sessions WHERE id=?',(id,)).fetchone()
            if not row: raise KeyError(id)
            if row['status']=='COMPLETED': return False
            if row['lease_owner'] and float(row['lease_until'] or 0)>now and row['lease_owner']!=owner: return False
            unknown=c.execute("SELECT count(*) FROM model_calls WHERE session_id=? AND status='STARTED'",(id,)).fetchone()[0]
            state=json.loads(row['payload']); state['unknown_calls']+=unknown
            if unknown:
                c.execute("UPDATE model_calls SET status='UNKNOWN' WHERE session_id=? AND status='STARTED'",(id,))
                self._event(c,id,row['turn_id'],'model_unknown',{'count':unknown})
            c.execute('UPDATE audit_sessions SET lease_owner=?,lease_until=?,revision=revision+1,payload=?,updated_at=? WHERE id=?',(owner,str(now+ttl),pack(state),timestamp(),id))
            return True
    def renew(self,id,owner,ttl=180):
        with self.db.connect() as c:
            changed=c.execute('UPDATE audit_sessions SET lease_until=?,updated_at=? WHERE id=? AND lease_owner=? AND CAST(lease_until AS REAL)>?',(str(time.time()+ttl),timestamp(),id,owner,time.time())).rowcount
            return changed==1
    def get(self,id):
        with self.db.connect() as c:
            row=c.execute('SELECT * FROM audit_sessions WHERE id=?',(id,)).fetchone()
            if not row: raise KeyError(id)
            return dict(row),json.loads(row['payload'])
    def transition(self,id,owner,expected_rev,status,state,kind,payload,*,model_result=None,tool_result=None,guardrail_events=None):
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE'); row=c.execute('SELECT * FROM audit_sessions WHERE id=?',(id,)).fetchone()
            if not row or row['lease_owner']!=owner or row['revision']!=expected_rev or float(row['lease_until'] or 0)<=time.time(): raise Conflict('执行权或版本已变化。')
            if tool_result:
                call_id=tool_result['call_id']; turn=row['turn_id']
                if c.execute('SELECT 1 FROM tool_receipts WHERE session_id=? AND turn_id=? AND call_id=?',(id,turn,call_id)).fetchone(): raise Conflict('工具调用已提交。')
                for e in tool_result['evidence']:
                    if not c.execute('SELECT 1 FROM evidence_artifacts WHERE id=?',(e,)).fetchone(): raise Conflict('证据尚未缓存。')
                    c.execute('INSERT OR IGNORE INTO session_evidence VALUES (?,?)',(id,e))
                cur=c.execute('INSERT INTO tool_traces(session_id,turn_id,repo,commit_sha,tool_name,status,created_at,payload) VALUES (?,?,?,?,?,?,?,?)',(id,turn,tool_result['repo'],tool_result['commit'],tool_result['name'],tool_result['status'],timestamp(),pack({'args':tool_result['args'],'duration_ms':tool_result['duration_ms'],'evidence_ids':tool_result['evidence'],'status':tool_result['status'],'result':tool_result['result']})))
                c.execute('INSERT INTO tool_receipts VALUES (?,?,?,?)',(id,turn,call_id,cur.lastrowid))
            if model_result:
                changed=c.execute("UPDATE model_calls SET status='COMPLETED',input_tokens=?,output_tokens=?,elapsed_ms=?,payload=? WHERE id=? AND status='STARTED'",(model_result['usage'].get('input_tokens',0),model_result['usage'].get('output_tokens',0),model_result['elapsed_ms'],pack({'usage':model_result['usage'],'public_output':model_result.get('public_output','')}),model_result['id'])).rowcount
                if changed!=1: raise Conflict('模型调用状态已变化。')
            for event in guardrail_events or []: self._event(c,id,row['turn_id'],'guardrail_triggered',event)
            self._event(c,id,row['turn_id'],kind,payload)
            c.execute('UPDATE audit_sessions SET status=?,revision=revision+1,payload=?,pending_operation=?,last_tool_call_id=?,lease_until=?,updated_at=? WHERE id=?',(status,pack(state),None if model_result else row['pending_operation'],tool_result['call_id'] if tool_result else row['last_tool_call_id'],str(time.time()+180),timestamp(),id))
    def begin_model(self,id,owner,expected_rev,role,model,state,input_reserve):
        call_id=uuid.uuid4().hex
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE'); row=c.execute('SELECT * FROM audit_sessions WHERE id=?',(id,)).fetchone()
            if not row or row['lease_owner']!=owner or row['revision']!=expected_rev or float(row['lease_until'] or 0)<=time.time(): raise Conflict('执行权或版本已变化。')
            c.execute('INSERT INTO model_calls(id,session_id,turn_id,role,status,model,created_at,payload) VALUES (?,?,?,?,?,?,?,?)',(call_id,id,row['turn_id'],role,'STARTED',model,timestamp(),pack({'reserved_input':input_reserve,'reserved_output':2048})))
            self._event(c,id,row['turn_id'],'model_started',{'role':role})
            c.execute('UPDATE audit_sessions SET revision=revision+1,payload=?,pending_operation=?,lease_until=?,updated_at=? WHERE id=?',(pack(state),'model:'+call_id,str(time.time()+180),timestamp(),id))
        return call_id
    def reject_model(self,id,owner,call_id,message):
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM audit_sessions WHERE id=?',(id,)).fetchone()
            if not row or row['lease_owner']!=owner: raise Conflict('执行权已变化。')
            model=c.execute("SELECT payload FROM model_calls WHERE id=? AND status='STARTED'",(call_id,)).fetchone()
            if not model: raise Conflict('模型调用状态已变化。')
            reservation=json.loads(model['payload']); state=json.loads(row['payload'])
            state['reserved_input']=max(0,state['reserved_input']-reservation.get('reserved_input',0))
            state['reserved_output']=max(0,state['reserved_output']-reservation.get('reserved_output',0))
            changed=c.execute("UPDATE model_calls SET status='REJECTED',payload=? WHERE id=? AND status='STARTED'",(pack({'error':message}),call_id)).rowcount
            if changed!=1: raise Conflict('模型调用状态已变化。')
            self._event(c,id,row['turn_id'],'model_rejected',{'message':message})
            c.execute("UPDATE audit_sessions SET status='FAILED',pending_operation=NULL,payload=?,revision=revision+1,updated_at=? WHERE id=?",(pack(state),timestamp(),id))
    def release(self,id,owner,interrupted=False):
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE'); row=c.execute('SELECT * FROM audit_sessions WHERE id=?',(id,)).fetchone()
            if row and row['lease_owner']==owner:
                if interrupted and row['status'] not in ('COMPLETED','FAILED'):
                    self._event(c,id,row['turn_id'],'interrupted',{'reason':'执行中断，可恢复'})
                c.execute('UPDATE audit_sessions SET status=?,lease_owner=NULL,lease_until=NULL,revision=revision+1,updated_at=? WHERE id=?',('INTERRUPTED' if interrupted and row['status'] not in ('COMPLETED','FAILED') else row['status'],timestamp(),id))
    def finish(self,id,owner,revision,state,report,guardrail_events=None):
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE'); row=c.execute('SELECT * FROM audit_sessions WHERE id=?',(id,)).fetchone()
            if not row or row['lease_owner']!=owner or row['revision']!=revision or float(row['lease_until'] or 0)<=time.time(): raise Conflict('执行权或版本已变化。')
            version=state['report_version']+1; state['report_version']=version
            c.execute('INSERT INTO harness_reports VALUES (?,?,?,?,?)',(id,version,row['turn_id'],pack(report),timestamp()))
            for event in guardrail_events or []: self._event(c,id,row['turn_id'],'guardrail_triggered',event)
            self._event(c,id,row['turn_id'],'report_ready',{'version':version})
            c.execute("UPDATE audit_sessions SET status='COMPLETED',revision=revision+1,payload=?,pending_operation=NULL,updated_at=? WHERE id=?",(pack(state),timestamp(),id))
    def public(self,id):
        row,state=self.get(id)
        with self.db.connect() as c:
            reports=[json.loads(x['payload']) for x in c.execute('SELECT payload FROM harness_reports WHERE session_id=? ORDER BY version',(id,))]
            events=[{'id':x['event_seq'],'type':x['event_type'],'data':json.loads(x['payload'])} for x in c.execute('SELECT * FROM audit_events WHERE session_id=? ORDER BY event_seq',(id,))]
        remaining=max(0,int(float(row['lease_until'] or 0)-time.time()+0.999)) if row['lease_owner'] else 0
        return {'id':id,'status':row['status'],'lease_busy':remaining>0,'retry_after':remaining,'revision':row['revision'],'turn_id':row['turn_id'],'bindings':state['bindings'], 'criteria':state['criteria'],'usage':state['usage'],'unknown_calls':state['unknown_calls'],'reports':reports,'events':events}
    def followup(self,id,query):
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE'); row=c.execute('SELECT * FROM audit_sessions WHERE id=?',(id,)).fetchone()
            if not row: raise KeyError(id)
            if row['status']!='COMPLETED' or row['lease_owner']: raise Conflict('任务运行中或尚未完成。')
            state=json.loads(row['payload'])
            previous=c.execute('SELECT payload FROM harness_reports WHERE session_id=? ORDER BY version DESC LIMIT 1',(id,)).fetchone()
            prior=None
            if previous:
                report=json.loads(previous['payload']); repositories=[]
                for item in report.get('repositories',[]):
                    rows=[]
                    for verdict in item.get('rows',[]):
                        refs=[]
                        for citation in verdict.get('citations',[]):
                            record=c.execute('SELECT source_type,path,start_line,end_line,source_url FROM evidence_artifacts WHERE id=?',(citation['evidence_id'],)).fetchone()
                            if record: refs.append({'evidence_id':citation['evidence_id'],**dict(record)})
                        rows.append({'criterion_id':verdict['criterion_id'],'status':verdict['status'],'summary':verdict['summary'][:400],'evidence':refs})
                    repositories.append({'binding':item['binding'],'rows':rows})
                prior={'query':report.get('query','')[:1500],'criteria':report.get('criteria',[]),'repositories':repositories}
            state.update(stage='plan',query=query,prior_context=prior,criteria=[],repo_index=0,summaries=[],history=[],context_id=uuid.uuid4().hex,ranges={},outlines=[],visible_evidence=[],lead_calls=0,sub_calls={},tool_counts={},turn_usage={'input_tokens':0,'output_tokens':0,'total_tokens':0},turn_model_calls=0,turn_tool_calls=0,reserved_input=0,reserved_output=0)
            state.pop('pending_tool',None); state.pop('summary',None)
            turn=uuid.uuid4().hex
            c.execute("UPDATE audit_sessions SET status='INIT',turn_id=?,revision=revision+1,payload=?,pending_operation=NULL,updated_at=? WHERE id=?",(turn,pack(state),timestamp(),id))
            self._event(c,id,turn,'followup',{'query':query})
