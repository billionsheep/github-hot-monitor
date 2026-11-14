import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from evidence.agent_harness import Harness, current_injections, model_view
from evidence.config import Settings
from evidence.db import AuditDB
from evidence.guardrails import calibrate_verdict, missing_ranges, verify_verdict, wrap_untrusted
from evidence.harness_schemas import Verdict
from evidence.routing import choose_route, scoped_source_hints
from evidence.tools import AuditTools
from eval.run_eval import FrozenClient, FrozenProvider
from test_harness import message, function

SHA='a'*40
class ScriptedModel:
    model='fixture';v3_tools=True
    def __init__(self):self.calls=[]
    async def complete(self,role,instructions,inputs,allow_tools):
        self.calls.append((role,instructions,json.loads(json.dumps(inputs))))
        if role=='lead':
            value={'criteria':[{'id':'c1','title':'指定约束'}]} if 'criteria' in instructions else {'summary':'查看逐项结果。'}
        else:
            initial=json.loads(inputs[0]['content']);value={'rows':[{'criterion_id':initial['criteria'][0]['id'],**initial['binding'],'status':'UNVERIFIED','summary':'需要继续核查。','citations':[],'verification_basis':'insufficient','runtime_validation_required':True,'next_step':'补充证据','support_relation':'insufficient','gap_reason':'资料不足'}]}
        return {'output':[message(value)],'usage':{'input_tokens':10,'output_tokens':3,'total_tokens':13}}

class V3HarnessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=AuditDB(replace(Settings(),data_dir=Path(self.tmp.name)))
        self.repo='test/repo';self.binding={'repo':self.repo,'commit':SHA}
        self.db.put_snapshot({'id':'a','repo':self.repo,'sha':SHA,'created_at':'now'})
        self.files={'README.md':'MIT is mentioned.\n','pyproject.toml':'[project]\nrequires-python = ">=3.11"\n'}
        self.provider=FrozenProvider(self.db,{self.repo:{'files':self.files,'selected_files_only':False}})
    async def test_route_is_persisted_fast_skips_leads_and_followup_reroutes(self):
        model=ScriptedModel();h=Harness(self.db,model,self.provider)
        id=h.create(['a'],'pyproject.toml 声明的 Python 版本范围是否允许 Python 3.10？')
        _,before=h.store.get(id);self.assertEqual(before['execution_route']['route'],'fast')
        await h.run(id);self.assertFalse(any(x[0]=='lead' for x in model.calls));self.assertEqual(h.store.public(id)['reports'][0]['execution_route']['route'],'fast')
        h.store.followup(id,'比较 Python 3.10 和 Docker Compose 部署是否满足？')
        _,state=h.store.get(id);self.assertEqual(state['execution_route']['route'],'full');await h.run(id)
        self.assertTrue(any(x[0]=='lead' for x in model.calls));self.assertEqual(len(h.store.public(id)['reports']),2)
    async def test_fast_route_resumes_persisted_and_force_full(self):
        model=ScriptedModel()
        async def crash(name,detail):
            if name=='model_response_before_commit':raise RuntimeError('stop')
        h=Harness(self.db,model,self.provider,hook=crash);id=h.create(['a'],'Python 3.11 是否支持？')
        with self.assertRaises(RuntimeError):await h.run(id)
        _,state=h.store.get(id);self.assertEqual(state['execution_route']['route'],'fast')
        await Harness(self.db,model,self.provider).run(id);self.assertEqual(h.store.public(id)['reports'][0]['execution_route']['route'],'fast')
        forced=h.create(['a'],'Python 3.11 是否支持？',force_full=True);self.assertEqual(h.store.public(forced)['execution_route']['route'],'full')
    async def test_routing_is_conservative(self):
        b=[self.binding];self.assertEqual(choose_route('Python 3.11 是否支持？',b,'deploy_readiness')['route'],'fast')
        for query in ('Python 3.11 和 Docker Compose 能否部署？','Python 3.11 与 Python 3.10 是否均支持？','README.md 和 pyproject.toml 是否支持 Python 3.11？','请分析架构和安全','是否可靠？'):
            self.assertEqual(choose_route(query,b,'deploy_readiness')['route'],'full',query)
        self.assertEqual(choose_route('Python 3.11 是否支持？',b*2,'deploy_readiness')['route'],'full')
        self.assertEqual(choose_route('Python 3.11 是否支持？',b,'arch_research')['route'],'full')
    async def test_auto_prefetch_uses_hint_and_injects_full_long_statement(self):
        self.files['src/gateway.py']='# filler\n'*223+'client = create_client(\n    note="'+('x'*400)+'",\n    base_url="VERIFY_AFTER_240",\n)\n'
        model=ScriptedModel();h=Harness(self.db,model,self.provider)
        id=h.create(['a'],'请检查 src/gateway.py 中 base_url 是否配置。',workflow_mode='arch_research');await h.run(id)
        subs=[x for x in model.calls if x[0]=='sub'];self.assertTrue(subs)
        initial=json.loads(subs[0][2][0]['content']);self.assertIn('src/gateway.py',initial['source_hints']['paths']);self.assertIn('base_url',initial['source_hints']['symbols'])
        outputs=[x['content'] for x in subs[0][2][1:] if x.get('role')=='user'];self.assertTrue(outputs)
        self.assertIn('VERIFY_AFTER_240',outputs[-1]);self.assertIn('x'*350,outputs[-1])
        self.assertTrue(any(c['name']=='read_file_lines' and c['args']['start_line']<=226<=c['args']['end_line'] for c in self.provider.calls))
    async def test_auto_prefetch_injects_complete_kwargs_transfer_chain(self):
        self.files['src/gateway.py']='''class Provider:
    base_url: str | None = None
    def _get_client_params(self):
        base_params = {
            "base_url": self.base_url,
        }
        client_params = {k: v for k, v in base_params.items() if v is not None}
        return client_params
    def client(self):
        client_params = self._get_client_params()
        self.client = OpenAIClient(**client_params)
'''
        model=ScriptedModel();h=Harness(self.db,model,self.provider);id=h.create(['a'],'检查 src/gateway.py 中 base_url 如何传递。',workflow_mode='arch_research');await h.run(id)
        inputs=next(x[2] for x in model.calls if x[0]=='sub');joined='\n'.join(json.dumps(json.loads(x['content'][x['content'].index('>')+1:x['content'].rindex('</untrusted>')]),ensure_ascii=False) for x in inputs if x.get('role')=='user' and x.get('content','').startswith('<untrusted ')).replace('\\"','"')
        for text in ('base_url: str','"base_url": self.base_url','client_params = {k: v','return client_params','client_params = self._get_client_params()','OpenAIClient(**client_params)'):self.assertIn(text,joined)
        reads=[x for x in self.provider.calls if x['name']=='read_file_lines'];self.assertLessEqual(len(reads),3)
    async def test_source_hints_extra_is_removed_but_citations_still_checked(self):
        self.files['compose.yaml']='services:\n  app:\n    ports:\n      - "8080:8000"\n'
        for invalid_quote in (False,True):
            class EchoModel(ScriptedModel):
                async def complete(model,role,instructions,inputs,allow_tools):
                    if role=='lead':return await super().complete(role,instructions,inputs,allow_tools)
                    responses=[x for x in inputs if x.get('type')=='function_call_output']
                    if not responses:return {'output':[function('read_file_lines',{'path':'compose.yaml','start_line':1,'end_line':4},'read')],'usage':{'input_tokens':5,'output_tokens':2}}
                    raw=responses[-1]['output'];data=json.loads(raw[raw.index('>')+1:raw.rindex('</untrusted>')]);e=data['parts'][0]['evidence'][0];initial=json.loads(inputs[0]['content'])
                    row={'criterion_id':initial['criteria'][0]['id'],**initial['binding'],'status':'PASS','summary':'端口声明 ['+e['evidence_id']+']','citations':[{'evidence_id':e['evidence_id'],'quote':'missing' if invalid_quote else '8080:8000'}],'verification_basis':'static_config','runtime_validation_required':False,'next_step':'检查配置','support_relation':'supports','gap_reason':None,'source_hints':{'paths':['compose.yaml'],'symbols':[]}}
                    return {'output':[message({'rows':[row]})],'usage':{'input_tokens':5,'output_tokens':2}}
            h=Harness(self.db,EchoModel(),self.provider);id=h.create(['a'],'核查 compose.yaml 端口声明',force_full=True);await h.run(id);public=h.store.public(id)
            self.assertEqual(public['reports'][0]['repositories'][0]['rows'][0]['status'],'UNVERIFIED' if invalid_quote else 'PASS')
            self.assertTrue(any(e['type']=='schema_repaired' for e in public['events']))
    async def test_truncated_json_gets_one_bounded_retry(self):
        for always_broken in (False,True):
            class TruncatedModel(ScriptedModel):
                def __init__(model):super().__init__();model.sub_count=0
                async def complete(model,role,instructions,inputs,allow_tools):
                    if role=='sub':
                        model.sub_count+=1
                        if always_broken or model.sub_count==1:
                            return {'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'{"rows":[{"summary":"截断'}]}],'usage':{'input_tokens':10,'output_tokens':5}}
                        self.assertIn('短摘要',inputs[-1]['content'])
                    return await super().complete(role,instructions,inputs,allow_tools)
            model=TruncatedModel();h=Harness(self.db,model,self.provider);id=h.create(['a'],'检查安全线索',workflow_mode='sec_sentinel');await h.run(id);events=h.store.public(id)['events']
            self.assertEqual(model.sub_count,2);self.assertEqual(sum(e['type']=='schema_retry' for e in events),1)
            self.assertEqual(any(e['type']=='sub_schema_error' for e in events),always_broken)
    async def test_ast_hints_follow_field_dictionary_and_kwargs_call(self):
        self.files['chat.py']='class Provider:\n    base_url: str | None = None\n    def params(self):\n        base_params = {\n            "base_url": self.base_url,\n        }\n        client_params = {k: v for k, v in base_params.items() if v is not None}\n        return client_params\n    def client(self):\n        client_params = self.params()\n        return OpenAIClient(**client_params)\n'
        tools=AuditTools(self.binding,FrozenClient(self.db,{'files':self.files}))
        by_url=await tools.get_markdown_outline({**self.binding,'path':'chat.py','symbol_or_param_hint':'base_url'})
        entries=by_url.facts[0].entries;self.assertTrue(any(e.kind=='AnnAssign' and e.start_line==2 for e in entries));self.assertTrue(any(e.kind=='Assign' and (e.start_line,e.end_line)==(4,6) for e in entries))
        by_params=await tools.get_markdown_outline({**self.binding,'path':'chat.py','symbol_or_param_hint':'client_params'})
        self.assertTrue(any(e.kind=='Call' and e.start_line==11 and e.calls[0]['keyword_arguments']==[{'name':'**','value':'client_params'}] for e in by_params.facts[0].entries))
    async def test_request_pruning_removes_old_coverage_and_allows_reload(self):
        model=ScriptedModel();h=Harness(self.db,model,self.provider)
        def pair(n):
            ev={'source_type':'file_lines','evidence_id':f'ev_{n}','path':'f.py','start_line':n,'end_line':n,'partial_line':False,'text':str(n)*7000,'context_excerpt':False}
            return [{'type':'function_call','name':'read_file_lines','call_id':str(n),'arguments':'{}'}, {'type':'function_call_output','call_id':str(n),'output':wrap_untrusted(json.dumps({'evidence':[ev]}),'tool-result')}]
        state={'history':sum((pair(n) for n in (1,2,3)),[]),'budget':{'input_tokens':60000},'turn_usage':{'input_tokens':0},'reserved_input':0}
        current_injections(state);self.assertEqual(len(state['ranges']['f.py']),3)
        initial={'role':'user','content':'{}'};h.fit_context(state,initial,'instructions',True)
        self.assertTrue(state['context_pruned']);self.assertEqual(missing_ranges(1,1,state['ranges'].get('f.py',[])),[(1,1)]);self.assertIn('移出',initial['content'])
    async def test_pruning_preserves_automatic_source_reads_for_final_request(self):
        h=Harness(self.db,ScriptedModel(),self.provider)
        e={'source_type':'file_lines','evidence_id':'ev_auto','path':'chat.py','start_line':4,'end_line':4,'partial_line':False,'text':'base_url = value\n','context_excerpt':False}
        auto=wrap_untrusted(json.dumps({'automatic_source_reads':1,'parts':[{'facts':[{'kind':'python_ast','path':'chat.py','entries':[{'title':'base_url'}]}]},{'evidence':[e]}]}),'tool-result')
        def pair(n):
            ev={'source_type':'file_lines','evidence_id':f'ev_{n}','path':'f.py','start_line':n,'end_line':n,'partial_line':False,'text':'x'*9000,'context_excerpt':False}
            return [{'type':'function_call','name':'read_file_lines','call_id':str(n),'arguments':'{}'},{'type':'function_call_output','call_id':str(n),'output':wrap_untrusted(json.dumps({'evidence':[ev]}),'tool-result')}]
        state={'history':[{'role':'user','content':auto},*pair(1),*pair(2),*pair(3)],'budget':{'input_tokens':60000},'turn_usage':{'input_tokens':0},'reserved_input':0}
        h.fit_context(state,{'role':'user','content':'{}'},'instructions',True)
        self.assertIn('ev_auto',state['visible_evidence']);self.assertEqual(state['ranges']['chat.py'],[[4,4]])
        self.assertTrue(any('base_url = value' in x.get('content','') for x in state['history']))
    async def test_real_stdio_outline_in_request_unlocks_source_read(self):
        fixtures=json.loads(Path('eval/v3/mcp_fixture.json').read_text());repo='modelcontextprotocol/python-sdk';fixture=fixtures[repo]
        self.db.put_snapshot({'id':'mcp','repo':repo,'sha':fixture['commit'],'created_at':'now'});provider=FrozenProvider(self.db,fixtures);h=Harness(self.db,ScriptedModel(),provider)
        id=h.create(['mcp'],'分析 stdio',workflow_mode='arch_research');owner='test-stdio';self.assertTrue(h.store.acquire(id,owner));binding={'repo':repo,'commit':fixture['commit']}
        path='src/mcp/server/stdio.py';row,state=h.store.get(id)
        call={'name':'get_markdown_outline','arguments':json.dumps({'path':path,'symbol_or_param_hint':None}),'call_id':'outline'}
        await h.run_tool(id,owner,row,state,binding,call);row,state=h.store.get(id)
        self.assertIn(path,state['outlines']);self.assertIn('python_ast',state['history'][-1]['output'])
        call={'name':'read_file_lines','arguments':json.dumps({'path':path,'start_line':1,'end_line':20}),'call_id':'read'}
        await h.run_tool(id,owner,row,state,binding,call);_,state=h.store.get(id)
        self.assertNotIn('当前上下文尚未读取大纲',state['history'][-1]['output']);self.assertIn(path,state['ranges']);h.store.release(id,owner)
    async def test_large_structured_outline_is_registered_without_raw_json_excerpt(self):
        entries=[{'kind':'FunctionDef','title':'function_'+str(i),'start_line':i+1,'end_line':i+1,'symbols':['x'*350 for _ in range(12)]} for i in range(30)]
        result={'tool':'get_markdown_outline','facts':[{'kind':'python_ast','path':'long.py','total_lines':200,'entries':entries}],'evidence':[{'source_type':'file_outline','evidence_id':'outline_x','path':'long.py','text':'X'*50000}],'coverage':{}}
        view,_=model_view(result,14000);self.assertEqual(view['facts'][0]['path'],'long.py');self.assertTrue(view['facts'][0]['entries']);self.assertGreater(view['facts'][0]['omitted_entries'],0)
        state={'history':[{'type':'function_call_output','call_id':'x','output':wrap_untrusted(json.dumps(view,ensure_ascii=False),'tool-result')}]};current_injections(state);self.assertIn('long.py',state['outlines'])
    async def test_real_mcp_architecture_scan_prioritizes_calls_across_files(self):
        fixtures=json.loads(Path('eval/v3/mcp_fixture.json').read_text());repo='modelcontextprotocol/python-sdk';fixture=fixtures[repo];binding={'repo':repo,'commit':fixture['commit']}
        result=await AuditTools(binding,FrozenClient(self.db,fixture)).analyze_architecture_profile(binding)
        data=json.loads(result.evidence[0].text);edges=data['edges'];paths={e['path'] for e in edges if e['signal']=='ast_call'}
        self.assertIn('src/mcp/client/stdio.py',paths);self.assertIn('src/mcp/server/stdio.py',paths)
        self.assertFalse(any(e['path']=='pyproject.toml' and '[tool.' in e['to'] for e in edges));self.assertLessEqual(len(edges),40)
    async def test_evicted_source_range_is_actually_reloaded(self):
        h=Harness(self.db,ScriptedModel(),self.provider);id=h.create(['a'],'核查文件',force_full=True);owner='test-owner';self.assertTrue(h.store.acquire(id,owner))
        call={'name':'read_file_lines','arguments':json.dumps({'path':'README.md','start_line':1,'end_line':1}),'call_id':'first'}
        row,state=h.store.get(id);await h.run_tool(id,owner,row,state,self.binding,call)
        row,state=h.store.get(id);self.assertEqual(len([x for x in self.provider.calls if x['name']=='read_file_lines']),1)
        state['history']=[];call['call_id']='second';await h.run_tool(id,owner,row,state,self.binding,call)
        self.assertEqual(len([x for x in self.provider.calls if x['name']=='read_file_lines']),2);h.store.release(id,owner)
    async def test_old_checkpoint_uses_full_route(self):
        model=ScriptedModel();h=Harness(self.db,model,self.provider);id=h.create(['a'],'Python 3.11 是否支持？')
        with self.db.connect() as c:
            row=c.execute('SELECT payload FROM audit_sessions WHERE id=?',(id,)).fetchone();state=json.loads(row['payload'])
            state.pop('v3');state.pop('execution_route');state.pop('workflow_mode');state.pop('force_full')
            c.execute('UPDATE audit_sessions SET payload=? WHERE id=?',(json.dumps(state),id))
        await h.run(id);self.assertTrue(any(x[0]=='lead' for x in model.calls))
    async def test_long_auto_reads_are_whole_or_explicitly_omitted(self):
        def read(n):
            raw='client = factory(\n'+('    parameter_value = 123456789012345678901234567890,\n'*80)+f'    base_url="TAIL_{n}",\n)\n'
            ev={'source_type':'file_lines','evidence_id':f'ev_{n}','repo':self.repo,'commit':SHA,'path':f'f{n}.py','start_line':1,'end_line':83,'partial_line':False,'text':raw}
            return {'tool':'read_file_lines','evidence':[ev],'coverage':{'complete':True}}
        parts=[read(n) for n in range(3)];result={'tool':'get_markdown_outline','facts':[],'evidence':[],'coverage':{},'auto_reads':parts}
        view,included=model_view(result,14000);shown={x['evidence'][0]['evidence_id']:x['evidence'][0]['text'] for x in view['parts'] if x.get('evidence')}
        omitted={x['path'] for x in view['omitted_reads']};self.assertTrue(shown);self.assertTrue(omitted)
        for part in parts:
            e=part['evidence'][0]
            if e['evidence_id'] in shown:self.assertEqual(shown[e['evidence_id']],e['text']);self.assertIn(e['evidence_id'],included)
            else:self.assertIn(e['path'],omitted)
        self.assertLessEqual(len(wrap_untrusted(json.dumps(view,ensure_ascii=False),'tool-result').encode()),14000)
    async def test_calibration_event_persisted_once_with_reason(self):
        for bad_quote in (True,False):
            class CalibrationModel(ScriptedModel):
                async def complete(model,role,instructions,inputs,allow_tools):
                    if role=='lead':return await super().complete(role,instructions,inputs,allow_tools)
                    initial=json.loads(inputs[0]['content']);outputs=[x for x in inputs if x.get('type')=='function_call_output']
                    if not outputs:out=[function('read_file_lines',{'path':'README.md','start_line':1,'end_line':1},'read-1')]
                    else:
                        raw=outputs[-1]['output'];data=json.loads(raw[raw.index('>')+1:raw.rindex('</untrusted>')]);ev=data['parts'][0]['evidence'][0]
                        row={'criterion_id':initial['criteria'][0]['id'],**initial['binding'],'status':'PASS','summary':'判断 ['+ev['evidence_id']+']','citations':[{'evidence_id':ev['evidence_id'],'quote':'not-in-source' if bad_quote else 'MIT'}], 'verification_basis':'declaration','runtime_validation_required':True,'next_step':'核查','support_relation':'supports' if bad_quote else 'insufficient','gap_reason':None if bad_quote else '缺少资料'}
                        out=[message({'rows':[row]})]
                    return {'output':out,'usage':{'input_tokens':5,'output_tokens':2,'total_tokens':7}}
            h=Harness(self.db,CalibrationModel(),self.provider);id=h.create(['a'],'核查声明',force_full=True);await h.run(id)
            events=[e for e in h.store.public(id)['events'] if e['type']=='status_calibrated'];self.assertEqual(len(events),1)
            data=events[0]['data'];self.assertEqual((data['original_status'],data['calibrated_status']),('PASS','UNVERIFIED'))
            self.assertEqual(data['reason_type'],'citation_invalid' if bad_quote else 'support_insufficient');self.assertTrue(data['reasons'])
    async def test_scoped_hints_preserve_each_multirepo_path(self):
        bindings=[{'repo':'pydantic/pydantic-ai','commit':SHA},{'repo':'agno-agi/agno','commit':'b'*40}]
        query='Pydantic AI 重点查看 pydantic_ai_slim/pydantic_ai/providers/openai.py，Agno 重点查看 libs/agno/agno/models/openai/chat.py。定位 base_url。'
        a=scoped_source_hints(query,bindings[0],bindings);b=scoped_source_hints(query,bindings[1],bindings)
        self.assertEqual(a['paths'],['pydantic_ai_slim/pydantic_ai/providers/openai.py']);self.assertEqual(b['paths'],['libs/agno/agno/models/openai/chat.py']);self.assertIn('base_url',a['symbols'])
    async def test_calibration_is_criterion_specific_and_accepts_license_text_in_readme(self):
        self.files['README-full.md']='Permission is hereby granted, free of charge, to any person obtaining a copy.\nThe above copyright notice and this permission notice shall be included in all copies.\nTHE SOFTWARE IS PROVIDED AS IS, WITHOUT WARRANTY.\n'
        tools=AuditTools(self.binding,FrozenClient(self.db,{'files':self.files}))
        async def read(path,end):return (await tools.read_file_lines({**self.binding,'path':path,'start_line':1,'end_line':end})).evidence[0]
        py=await read('pyproject.toml',2);missing=await read('README.md',1);full=await read('README-full.md',3)
        def row(status,ev,quote,relation):return Verdict(criterion_id='x',**self.binding,status=status,summary='判断 ['+ev.evidence_id+']',citations=[{'evidence_id':ev.evidence_id,'quote':quote}],verification_basis='declaration',runtime_validation_required=False,next_step='核对',support_relation=relation)
        query='分别核查 Python 3.10 与 MIT 协议，缺少授权文本时不要推测。'
        failed,why=calibrate_verdict(row('FAIL',py,'>=3.11','contradicts'),query,self.db,criterion='Python 3.10 是否满足？',require_relation=True)
        self.assertEqual(failed.status,'FAIL');self.assertFalse(why)
        unverified,_=calibrate_verdict(row('PASS',missing,'MIT','supports'),query,self.db,criterion='是否采用 MIT 协议？',require_relation=True)
        self.assertEqual(unverified.status,'UNVERIFIED');self.assertEqual(unverified.original_status,'PASS');self.assertTrue(unverified.status_calibrated)
        passed,why=calibrate_verdict(row('PASS',full,'Permission is hereby granted','supports'),query,self.db,criterion='是否采用 MIT 协议？',require_relation=True)
        self.assertEqual(passed.status,'PASS');self.assertFalse(why)
        limited=row('PASS',py,'>=3.11','partial').model_copy(update={'gap_reason':'仅覆盖静态版本声明'})
        risk,why=calibrate_verdict(limited,'检查版本',self.db,criterion='版本范围',require_relation=True)
        self.assertEqual(risk.status,'RISK');self.assertEqual(risk.original_status,'PASS');self.assertTrue(why)
    async def test_security_zero_matches_cannot_prove_overall_security(self):
        result=await AuditTools(self.binding,FrozenClient(self.db,{'files':{'safe.py':'value = 1\n'}})).scan_security_and_risk_sinks(self.binding)
        artifact=result.evidence[0];row=Verdict(criterion_id='x',**self.binding,status='PASS',summary='无命中 ['+artifact.evidence_id+']',citations=[{'evidence_id':artifact.evidence_id,'quote':'"findings":[]'}],verification_basis='static_config',runtime_validation_required=False,next_step='核对',support_relation='supports')
        result,_=calibrate_verdict(row,'项目是否安全？',self.db,criterion='整个项目是否安全？',require_relation=True);self.assertEqual(result.status,'UNVERIFIED')
        result,_=calibrate_verdict(row,'扫描范围内是否命中？',self.db,criterion='扫描范围内是否有安全线索命中？',require_relation=True);self.assertEqual(result.status,'PASS')
    async def test_supported_security_risk_keeps_fact_and_runtime_gap(self):
        e=(await AuditTools(self.binding,FrozenClient(self.db,{'files':{'code.py':'run(command, shell=True)\n'}})).read_file_lines({**self.binding,'path':'code.py','start_line':1,'end_line':1})).evidence[0]
        row=Verdict(criterion_id='x',**self.binding,status='RISK',summary='存在 shell 执行路径 ['+e.evidence_id+']',citations=[{'evidence_id':e.evidence_id,'quote':'shell=True'}],verification_basis='static_config',runtime_validation_required=True,next_step='核查调用方',support_relation='supports',gap_reason='实际调用与信任边界尚未确认')
        result,why=calibrate_verdict(row,'审计进程执行安全',self.db,criterion='检查执行风险',require_relation=True);self.assertEqual(result.status,'RISK');self.assertFalse(why);self.assertEqual(result.gap_reason,row.gap_reason)
        for relation in ('insufficient','unknown'):
            result,_=calibrate_verdict(row.model_copy(update={'support_relation':relation}),'审计进程执行安全',self.db,criterion='检查执行风险',require_relation=True);self.assertEqual(result.status,'UNVERIFIED')
    async def test_missing_required_statement_downgrades_and_records_reason(self):
        fragment=(await AuditTools(self.binding,FrozenClient(self.db,{'files':self.files})).read_file_lines({**self.binding,'path':'README.md','start_line':1,'end_line':1})).evidence[0]
        h=Harness(self.db,ScriptedModel(),self.provider);id=h.create(['a'],'核查 base_url');
        with self.db.connect() as c:c.execute('INSERT INTO session_evidence VALUES (?,?)',(id,fragment.evidence_id))
        row=Verdict(criterion_id='c1',**self.binding,status='PASS',summary='声明 ['+fragment.evidence_id+']',citations=[{'evidence_id':fragment.evidence_id,'quote':'MIT'}],verification_basis='static_config',runtime_validation_required=True,next_step='继续',support_relation='supports')
        from evidence.harness_schemas import SubReport
        state={'v3':True,'criteria':[{'id':'c1','title':'base_url 配置'}],'query':'核查 base_url','visible_evidence':[fragment.evidence_id],'prefetch_expected':[{'path':'src/code.py','start_line':225,'end_line':230,'hint':'base_url'}],'ranges':{}}
        events=[];rows=h.verify_rows(id,state,self.binding,SubReport(rows=[row]),guard_events=events);self.assertEqual(rows[0]['status'],'UNVERIFIED');self.assertIn('未完整进入',rows[0]['gap_reason']);self.assertTrue(any(e.get('event_type')=='status_calibrated' for e in events))
