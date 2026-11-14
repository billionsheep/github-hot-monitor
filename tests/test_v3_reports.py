import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from fastapi.testclient import TestClient
from evidence.app import app
from evidence.agent_harness import Harness
from evidence.config import Settings
from evidence.db import AuditDB
from evidence.harness_schemas import IntegrationBlueprint
from evidence.report_v3 import valid_blueprint, validate_report_extras
from evidence.replay import make_bundle, read_bundle, sha
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
    async def test_license_candidates_are_scanned_as_docs(self):
        fixture={'files':{'LICENSE':'MIT License\nPermission is hereby granted.\n'},'selected_files_only':False}
        result=await AuditTools(self.binding,FrozenClient(self.db,fixture)).analyze_architecture_profile(self.binding)
        scope=json.loads(result.evidence[0].text)['scope'];self.assertIn('LICENSE',scope['files']);self.assertEqual(scope['file_categories']['doc'],1)
