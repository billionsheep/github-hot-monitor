import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from fastapi.testclient import TestClient
from evidence.app import app
from evidence.agent_harness import Harness, model_view
from evidence.config import Settings
from evidence.db import AuditDB
from evidence.harness_schemas import IntegrationBlueprint
from evidence.report_v3 import valid_blueprint, validate_report_extras, visible_texts, normalize_env_placeholders, config_syntax
from evidence.replay import make_bundle, read_bundle, sha, markdown
from evidence.tools import AuditTools
from evidence.workflows import workflows
from eval.run_eval import FrozenClient, FrozenProvider
from test_v3_harness import ScriptedModel

class ReportsV3Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=AuditDB(replace(Settings(),data_dir=Path(self.tmp.name)))
        fixtures=json.loads(Path('eval/v3/security_fixtures.json').read_text());self.fixtures=fixtures
        self.repo='eval/v3-exec';self.binding={'repo':self.repo,'commit':fixtures[self.repo]['commit']}
        self.db.put_snapshot({'id':'one','repo':self.repo,'sha':self.binding['commit'],'created_at':'now'})
        self.provider=FrozenProvider(self.db,fixtures)
    async def test_workflows_are_shared_api_and_static_build(self):
        with TestClient(app) as c:self.assertEqual(c.get('/api/workflows').json(),workflows())
        import subprocess,sys
        out=Path(self.tmp.name)/'public';subprocess.run([sys.executable,'ops/scripts/build_pages.py','--state-dir','data','--web-dir','web','--out-dir',str(out)],check=True,capture_output=True)
        self.assertEqual(json.loads((out/'workflows.json').read_text()),workflows())
    async def test_security_mode_runs_tool_and_model_receives_real_findings(self):
        model=ScriptedModel();h=Harness(self.db,model,self.provider);id=h.create(['one'],'检查进程线索',workflow_mode='sec_sentinel');await h.run(id)
        self.assertEqual(self.provider.calls[0]['name'],'scan_security_and_risk_sinks')
        sub=next(x for x in model.calls if x[0]=='sub');self.assertIn('scan_security_and_risk_sinks',sub[1]);output=''.join(x.get('content','') for x in sub[2][1:] if x.get('role')=='user')
        self.assertIn('derived_summary',output);self.assertIn('review_exec.py',output);self.assertIn('exec_sinks',output)
        report=h.store.public(id)['reports'][0];self.assertEqual(report['workflow_mode'],'sec_sentinel');self.assertTrue(report['security_findings']);self.assertTrue(report['analysis_metrics'])
        self.assertTrue(all(x['assessment']=='rule_hit' for x in report['security_findings'][0]['findings']))
        h.store.followup(id,'继续核对上下文');_,state=h.store.get(id);self.assertEqual(state['workflow_mode'],'sec_sentinel')
    async def test_requested_outputs_reach_model_and_missing_output_is_reported(self):
        for mode,query,key,expected in [
            ('deploy_readiness','检查配置并给出可复制的最小配置示例','integration_blueprint','配置示例未生成'),
            ('sec_sentinel','检查进程调用并给出上下文复核','security_reviews','上下文复核未形成')]:
            model=ScriptedModel();h=Harness(self.db,model,self.provider);id=h.create(['one'],query,workflow_mode=mode);await h.run(id)
            sub=next(x for x in model.calls if x[0]=='sub');initial=json.loads(sub[2][0]['content']);self.assertIn(key,initial['requested_outputs']);self.assertIn(key,sub[1])
            report=h.store.public(id)['reports'][0];self.assertTrue(any(expected in gap for gap in report['analysis_gaps']))
    async def test_security_cap_spreads_files_and_preferred_source_reaches_model(self):
        files={f'src/mcp/client/a{i}.py':'import os\n'+''.join(f'v{j} = os.getenv("KEY{j}")\n' for j in range(12)) for i in range(7)}
        path='src/mcp/client/stdio.py';files[path]='import os\nvalue = os.getenv("STDIO_KEY")\n'
        tools=AuditTools(self.binding,FrozenClient(self.db,{'files':files,'selected_files_only':False}));result=await tools.scan_security_and_risk_sinks({**self.binding,'path_prefix':'src/mcp/client','mode':'all'})
        artifact=next(e for e in result.evidence if e.source_type=='security_scan');data=json.loads(artifact.text)
        self.assertLessEqual(len(data['findings']),40);self.assertTrue(any(x['path']==path for x in data['findings']))
        view,_=model_view(result.model_dump(),14000,[path]);self.assertEqual(view['derived_summary']['entries'][0]['path'],path)
        self.assertTrue(any(x.get('path')==path and 'STDIO_KEY' in x.get('text','') for x in view['evidence']))
    async def test_requested_outputs_accept_evidence_backed_model_responses(self):
        class OutputModel(ScriptedModel):
            async def complete(model,role,instructions,inputs,allow_tools):
                if role=='lead':return await super().complete(role,instructions,inputs,allow_tools)
                initial=json.loads(inputs[0]['content']);visible=visible_texts(inputs);requested=initial['requested_outputs'];output={'rows':[]}
                if 'integration_blueprint' in requested:
                    eid=next(k for k,v in visible.items() if 'MODEL_BASE_URL' in v)
                    output['integration_blueprint']={'format':'env','content':'MODEL_BASE_URL=<user-supplied>','applicability':'设置模型服务地址','verification_steps':['检查连接'],'citations':[{'evidence_id':eid,'quote':'MODEL_BASE_URL'}]}
                else:
                    views=[]
                    for item in inputs:
                        raw=item.get('content','')
                        if raw.startswith('<untrusted '):views.append(json.loads(raw[raw.index('>')+1:raw.rindex('</untrusted>')]))
                    view=next(x for x in views if x.get('derived_summary'));f=next(x for x in view['derived_summary']['entries'] if x['evidence_id'] in visible)
                    e=next(x for x in view['evidence'] if x['evidence_id']==f['evidence_id']);lines=e['text'].splitlines();quote=lines[f['start_line']-e['start_line']].strip()
                    output['security_reviews']=[{k:f[k] for k in ('evidence_id','path','start_line','end_line')}|{'quote':quote,'explanation':'该调用的上下文仍需要检查实际输入来源。'}]
                from test_harness import message
                return {'output':[message(output)],'usage':{'input_tokens':10,'output_tokens':3}}
        files={'settings.py':'MODEL_BASE_URL = "http://localhost"\n'};fixture={self.repo:{'files':files,'selected_files_only':False}}
        h=Harness(self.db,OutputModel(),FrozenProvider(self.db,fixture));id=h.create(['one'],'检查 settings.py 的 MODEL_BASE_URL 并给配置示例');await h.run(id)
        public=h.store.public(id);r=public['reports'][0];self.assertEqual(len(r['integration_blueprint']),1);self.assertFalse(r['analysis_gaps'])
        self.assertEqual(r['integration_blueprint'][0]['blueprint']['content'],'MODEL_BASE_URL="<user-supplied>"');self.assertTrue(any(e['type']=='blueprint_format_normalized' and e['data']['lines']==1 for e in public['events']))
        h=Harness(self.db,OutputModel(),self.provider);id=h.create(['one'],'审计进程并进行上下文复核',workflow_mode='sec_sentinel');await h.run(id)
        r=h.store.public(id)['reports'][0];self.assertTrue(any(f.get('assessment')=='context_reviewed' for g in r['security_findings'] for f in g['findings']));self.assertFalse(r['analysis_gaps'])
    async def test_architecture_graph_and_replay_v2_reject_tampered_edge(self):
        h=Harness(self.db,ScriptedModel(),self.provider);id=h.create(['one'],'分析架构',workflow_mode='arch_research');await h.run(id)
        self.assertEqual(self.provider.calls[0]['name'],'analyze_architecture_profile')
        report=h.store.public(id)['reports'][0];self.assertTrue(report['architecture_graph']);self.assertTrue(report['architecture_graph'][0]['edges'])
        bundle=make_bundle(self.db,id);self.assertEqual(bundle['schema_version'],'2.0');payload=read_bundle(json.dumps(bundle,ensure_ascii=False).encode())
        edge=payload['session']['reports'][0]['architecture_graph'][0]['edges'][0];edge['evidence_id']='ev_forged'
        raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'));bundle['payload_json']=raw;bundle['sha256']=sha(raw)
        with self.assertRaises(ValueError):read_bundle(json.dumps(bundle,ensure_ascii=False).encode())
    async def test_blueprint_syntax_binding_and_visible_quote(self):
        files={'settings.py':'MODEL_BASE_URL = "http://localhost"\n'};fixture={'files':files};tools=AuditTools(self.binding,FrozenClient(self.db,fixture))
        e=(await tools.read_file_lines({**self.binding,'path':'settings.py','start_line':1,'end_line':1})).evidence[0]
        b={'format':'python','content':'MODEL_BASE_URL = "<user-supplied>"','applicability':'仅适用于使用此环境配置的项目。','verification_steps':['在测试环境核对连接。'],'citations':[{'evidence_id':e.evidence_id,'quote':'MODEL_BASE_URL'}]}
        self.assertTrue(valid_blueprint(b,self.binding,self.db.get_evidence,{e.evidence_id:e.text}))
        bad={**b,'content':'MODEL_BASE_URL ='};self.assertFalse(valid_blueprint(bad,self.binding,self.db.get_evidence,{e.evidence_id:e.text}))
        self.assertFalse(valid_blueprint(b,{**self.binding,'repo':'other/repo'},self.db.get_evidence,{e.evidence_id:e.text}))
        self.assertFalse(valid_blueprint(b,self.binding,self.db.get_evidence,{e.evidence_id:'omitted'}))
    async def test_env_placeholder_normalization_is_narrow_and_keeps_evidence_gate(self):
        raw='OPENAI_BASE_URL=<user-supplied>\nOPENAI_API_KEY=<user-supplied>\n';fixed,count=normalize_env_placeholders(raw)
        self.assertEqual(count,2);self.assertEqual(fixed,'OPENAI_BASE_URL="<user-supplied>"\nOPENAI_API_KEY="<user-supplied>"\n')
        self.assertFalse(config_syntax('env',raw));self.assertTrue(config_syntax('env',fixed))
        for line in ('KEY=<x>suffix','KEY=<x>; echo bad','KEY="<x>"','KEY=<$(danger)>','KEY=<x> # trailing','KEY=prefix<x>'):
            self.assertEqual(normalize_env_placeholders(line),(line,0))
        fixture={'files':{'settings.py':'OPENAI_BASE_URL = "http://localhost"\n'}};e=(await AuditTools(self.binding,FrozenClient(self.db,fixture)).read_file_lines({**self.binding,'path':'settings.py','start_line':1,'end_line':1})).evidence[0]
        b={'format':'env','content':fixed,'applicability':'配置服务','verification_steps':['检查连接'],'citations':[{'evidence_id':e.evidence_id,'quote':'OPENAI_BASE_URL'}]}
        self.assertFalse(valid_blueprint(b,self.binding,self.db.get_evidence,{e.evidence_id:e.text}))
        b['content']='OPENAI_BASE_URL="<user-supplied>"';self.assertFalse(valid_blueprint(b,self.binding,self.db.get_evidence,{e.evidence_id:'omitted'}))
    async def test_blueprint_identifiers_and_markdown_provenance(self):
        fixture={'files':{'settings.py':'NOT_MODEL_BASE_URL = "http://localhost"\nMODEL_BASE_URL = "http://localhost"\n'}}
        e=(await AuditTools(self.binding,FrozenClient(self.db,fixture)).read_file_lines({**self.binding,'path':'settings.py','start_line':1,'end_line':2})).evidence[0]
        b={'format':'env','content':'MODEL_BASE_URL="<user-supplied>"','applicability':'适用于任何生产项目','verification_steps':['检查连接'],'citations':[{'evidence_id':e.evidence_id,'quote':'NOT_MODEL_BASE_URL'}]}
        self.assertFalse(valid_blueprint(b,self.binding,self.db.get_evidence,{e.evidence_id:e.text}))
        b['citations'][0]['quote']='MODEL_BASE_URL = "http://localhost"'
        self.assertTrue(valid_blueprint(b,self.binding,self.db.get_evidence,{e.evidence_id:e.text}))
        session={'id':'test','status':'COMPLETED','reports':[{'repositories':[],'integration_blueprint':[{**self.binding,'blueprint':b}]}]}
        output=markdown(session,{e.evidence_id:e.model_dump()})
        self.assertIn(f"依据范围：{self.repo} @ {self.binding['commit']}",output)
        self.assertIn('模型提出的适用条件（待核验）',output)
        self.assertIn(e.source_url,output);self.assertIn(e.evidence_id,output)
    async def test_review_must_quote_the_finding_range(self):
        h=Harness(self.db,ScriptedModel(),self.provider);id=h.create(['one'],'检查进程线索',workflow_mode='sec_sentinel');await h.run(id)
        p=read_bundle(json.dumps(make_bundle(self.db,id),ensure_ascii=False).encode());r=p['session']['reports'][0]
        f=next(x for x in r['security_findings'][0]['findings'] if x['path']=='review_exec.py');e=p['evidence'][f['evidence_id']]
        self.assertGreater(f['start_line'],e['start_line'])
        f['assessment']='context_reviewed';f['review']={'quote':'import subprocess as proc','explanation':'已经核查相关代码上下文。'}
        with self.assertRaises(ValueError):validate_report_extras(r,p['evidence'].get)
        f['review']['quote']='return'
        with self.assertRaises(ValueError):validate_report_extras(r,p['evidence'].get)
        f['review']['quote']='shell=True';self.assertTrue(validate_report_extras(r,p['evidence'].get))
    async def test_license_candidates_are_scanned_as_docs(self):
        fixture={'files':{'LICENSE':'MIT License\nPermission is hereby granted.\n'},'selected_files_only':False}
        result=await AuditTools(self.binding,FrozenClient(self.db,fixture)).analyze_architecture_profile(self.binding)
        scope=json.loads(result.evidence[0].text)['scope'];self.assertIn('LICENSE',scope['files']);self.assertEqual(scope['file_categories']['doc'],1)
