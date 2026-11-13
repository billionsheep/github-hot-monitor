import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from evidence import agent
from evidence.app import app

REQ = agent.RunInput(repository='test/repo', requirements=[{'id':'python','category':'python','description':'支持 Python 3.11'}])
SNAP = {'id':'snap', 'repo':'test/repo', 'sha':'a'*40, 'created_at':'now'}
CONFIG = {'key':'test-only-secret', 'base_url':'https://api.openai.com/v1','model':'gpt-6.1-sol','format':'responses','effort':'low'}
def call(name, args, id='c1'):
    return {'type':'function_call','name':name,'arguments':json.dumps(args),'call_id':id}
def final(id='ev_valid', verdict='证据支持'):
    return {'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps({'rows':[{'requirement_id':'python','verdict':verdict,'rationale':'根据声明','evidence_ids':[id] if id else [],'next_checks':'安装验证'}]},ensure_ascii=False)}]}], 'usage':{'input_tokens':12,'output_tokens':5,'total_tokens':17}}
def job(): return {'status':'running','progress':[],'repository':None,'commit':None}
class AgentTests(unittest.TestCase):
    def test_loop_preserves_reasoning_and_limits_and_references(self):
        payloads=[]
        def transport(config,payload):
            payloads.append(json.loads(json.dumps(payload)))
            if len(payloads)==1:
                return {'output':[{'type':'reasoning','id':'rs_1','summary':[]},call('read_fragment',{'path':'README.md','start':1,'lines':20})], 'usage':{'input_tokens':10,'output_tokens':3,'total_tokens':13}}
            return final()
        def tool(name,args,snap,registry):
            registry['ev_valid']={'evidence_id':'ev_valid','path':'README.md','source_url':'https://github.com/test/repo/blob/a/README.md#L1'}
            return registry['ev_valid']
        j=job()
        with patch('evidence.app.create_snapshot',return_value=SNAP), patch.object(agent,'tool_call',side_effect=tool): agent.execute(j,CONFIG,REQ,transport)
        self.assertEqual(j['rows'][0]['verdict'],'证据支持'); self.assertEqual(j['tool_calls'],1)
        self.assertEqual(j['usage']['total_tokens'],30); self.assertEqual(j['model_requests'],2)
        self.assertEqual(payloads[0]['max_output_tokens'],2048); self.assertEqual(payloads[0]['reasoning']['effort'],'low')
        self.assertTrue(any(x.get('type')=='reasoning' for x in payloads[1]['input']))
        self.assertTrue(any(x.get('type')=='function_call_output' and x['call_id']=='c1' for x in payloads[1]['input']))
        self.assertEqual(j['evidence'][0]['evidence_id'],'ev_valid')
    def test_invalid_reference_and_unsupported_claim_downgrade(self):
        for report in (final('foreign'), final(None)):
            j=job()
            with patch('evidence.app.create_snapshot',return_value=SNAP): agent.execute(j,CONFIG,REQ,lambda *_: report)
            self.assertEqual(j['rows'][0]['verdict'],'信息不足'); self.assertEqual(j['evidence'],[])
    def test_insufficient_result_with_no_evidence(self):
        j=job()
        with patch('evidence.app.create_snapshot',return_value=SNAP): agent.execute(j,CONFIG,REQ,lambda *_: final(None,'信息不足'))
        self.assertEqual(j['rows'][0]['verdict'],'信息不足'); self.assertEqual(j['stop_reason'],'完成')
    def test_request_budget_and_tool_budget(self):
        calls=[]
        def transport(config,payload):
            calls.append(1)
            return {'output':[call('list_directory',{'path':''},f'call{len(calls)}-{i}') for i in range(3)]}
        j=job()
        with patch('evidence.app.create_snapshot',return_value=SNAP), patch.object(agent,'tool_call',return_value={'entries':[]}): agent.execute(j,CONFIG,REQ,transport)
        self.assertEqual(j['model_requests'],6); self.assertEqual(j['tool_calls'],8)
        self.assertEqual(j['stop_reason'],'模型请求预算耗尽'); self.assertEqual(j['rows'][0]['verdict'],'信息不足')
    def test_tool_parameter_checks_and_snapshot_binding(self):
        with patch('evidence.app.get_tree',return_value={'entries':[],'truncated':False}) as tree:
            agent.tool_call('list_directory',{'path':'src'},SNAP,{})
            tree.assert_called_once_with('snap','src')
        for args in ({'path':'x','start':0,'lines':1},{'path':'x','start':1,'lines':201},{'path':'x','start':True,'lines':1},{'path':'x','start':1,'lines':1,'repo':'other'}):
            with self.assertRaises(ValueError): agent.tool_call('read_fragment',args,SNAP,{})
    def test_reserves_last_request_for_report(self):
        payloads=[]
        def transport(config,payload):
            payloads.append(payload)
            if payload.get('tool_choice') == 'none':
                return final(None,'信息不足')
            return {'output':[call('list_directory',{'path':''},f'c{len(payloads)}')]}
        j=job()
        with patch('evidence.app.create_snapshot',return_value=SNAP), patch.object(agent,'tool_call',return_value={'entries':[]}):
            agent.execute(j,CONFIG,REQ,transport)
        self.assertEqual(j['model_requests'],6)
        self.assertEqual(j['tool_calls'],5)
        self.assertEqual(j['stop_reason'],'完成')
        self.assertEqual(payloads[-1]['tool_choice'],'none')
        self.assertEqual(j['rows'][0]['verdict'],'信息不足')
    def test_missing_key_no_snapshot_or_model(self):
        with patch.object(agent,'configuration',return_value={**CONFIG,'key':''}), patch('evidence.app.create_snapshot') as snap:
            client=TestClient(app)
            self.assertFalse(client.get('/api/agent/config').json()['configured'])
            self.assertEqual(client.post('/api/agent/runs',json=REQ.model_dump()).status_code,503)
            snap.assert_not_called()
    def test_http_failure_is_sanitized_and_not_retried(self):
        fake=unittest.mock.Mock(status_code=401)
        j=job()
        with patch('evidence.app.create_snapshot',return_value=SNAP), patch('evidence.agent.httpx.post',return_value=fake) as post:
            agent.execute(j,CONFIG,REQ)
        self.assertEqual(post.call_count,1); self.assertEqual(j['model_requests'],1)
        self.assertNotIn(CONFIG['key'], json.dumps(j,ensure_ascii=False))
        self.assertIn('401',j['stop_reason'])
    def test_env_is_data_not_shell(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'.env.local').write_text('LLM_API_KEY=$(touch /tmp/agent-never-execute)\nLLM_MODEL=gpt-6.1-sol\n')
            with patch.object(agent,'ROOT',Path(folder)):
                self.assertEqual(agent.configuration()['key'],'$(touch /tmp/agent-never-execute)')
    def test_context_limit_stops_safely(self):
        j=job()
        with patch('evidence.app.create_snapshot',return_value=SNAP), patch.object(agent,'MAX_CONTEXT_BYTES',100): agent.execute(j,CONFIG,REQ,lambda *_: self.fail('must not call'))
        self.assertEqual(j['stop_reason'],'上下文预算耗尽'); self.assertEqual(j['model_requests'],0)

if __name__ == '__main__': unittest.main()
