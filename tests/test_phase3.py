import json
import tempfile
import unittest
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from evidence.app import app
from evidence.config import Settings
from evidence.db import AuditDB
from evidence.agent_harness import Harness
from evidence.replay import make_bundle,read_bundle,sha
from test_harness import FixtureModel, FixtureProvider, SHA_A, SHA_B

class Phase3Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=AuditDB(replace(Settings(),data_dir=Path(self.tmp.name)))
        for id,repo,commit in [('a','test/alpha',SHA_A),('b','test/beta',SHA_B)]:self.db.put_snapshot({'id':id,'repo':repo,'sha':commit,'created_at':'now'})
        h=Harness(self.db,FixtureModel(),FixtureProvider(self.db));self.id=h.create(['a','b'],'比较模型配置');await h.run(self.id)
    async def test_replay_integrity_and_foreign_citations(self):
        bundle=make_bundle(self.db,self.id); raw=json.dumps(bundle,ensure_ascii=False).encode(); payload=read_bundle(raw)
        self.assertEqual(payload['session']['id'],self.id);self.assertTrue(payload['evidence'])
        bad=dict(bundle,payload_json=bundle['payload_json']+' ')
        with self.assertRaises(ValueError):read_bundle(json.dumps(bad).encode())
        payload['session']['reports'][0]['repositories'][0]['rows'][0]['citations'][0]['evidence_id']='ev_foreign'
        text=json.dumps(payload,ensure_ascii=False);bad=dict(bundle,payload_json=text,sha256=sha(text))
        with self.assertRaises((ValueError,KeyError)):read_bundle(json.dumps(bad,ensure_ascii=False).encode())
        payload=read_bundle(raw);next(iter(payload['evidence'].values()))['source_url']='https://example.com/evil'
        text=json.dumps(payload,ensure_ascii=False);bad=dict(bundle,payload_json=text,sha256=sha(text))
        with self.assertRaises(ValueError):read_bundle(json.dumps(bad,ensure_ascii=False).encode())
    async def test_sessions_sse_evidence_export_and_health(self):
        with patch('evidence.harness_api.AuditDB',return_value=self.db),TestClient(app) as client:
            self.assertTrue(client.get('/api/health').json()['capabilities']['stream'])
            self.assertIn(self.id,[r['id'] for r in client.get('/api/audit/sessions').json()])
            detail=client.get('/api/audit/sessions/'+self.id).json();self.assertTrue(detail['traces'])
            ref=detail['reports'][0]['repositories'][0]['rows'][0]['citations'][0]['evidence_id']
            self.assertEqual(client.get(f'/api/audit/sessions/{self.id}/evidence/{ref}').status_code,200)
            self.assertEqual(client.get(f'/api/audit/sessions/missing/evidence/{ref}').status_code,404)
            response=client.get(f'/api/audit/sessions/{self.id}/stream?after=2',headers={'Last-Event-ID':'3'})
            self.assertIn('id: 4\n',response.text);self.assertNotIn('id: 3\n',response.text);self.assertIn('event: terminal',response.text)
            exported=client.get(f'/api/audit/sessions/{self.id}/export?format=replay');self.assertEqual(read_bundle(exported.content)['session']['id'],self.id)
            self.assertIn('test/alpha',client.get(f'/api/audit/sessions/{self.id}/export?format=markdown').text)
            self.assertEqual(client.get(f'/api/audit/sessions/{self.id}/export?format=other').status_code,422)
    async def test_pages_build_copies_replay_tree(self):
        out=Path(self.tmp.name)/'public'
        subprocess.run([sys.executable,'ops/scripts/build_pages.py','--state-dir','data','--web-dir','web','--out-dir',str(out)],check=True,capture_output=True)
        self.assertTrue((out/'replays'/'index.json').exists())
        self.assertTrue((out/'replays'/'fastapi-python311.json').exists())
    async def test_create_and_resume_are_idempotent(self):
        h=Harness(self.db,FixtureModel(),FixtureProvider(self.db));budget={'model_requests':20,'tool_calls':24,'input_tokens':60000,'output_tokens':16384}
        done=h.create(['a'],'检查','same-key',budget);await h.run(done)
        waiting=h.create(['a'],'等待');self.assertTrue(h.store.acquire(waiting,'other'))
        with patch('evidence.harness_api.AuditDB',return_value=self.db),TestClient(app) as client:
            with patch('evidence.harness_api.schedule',side_effect=AssertionError('completed task must not restart')):
                result=client.post('/api/audit/sessions',json={'snapshot_ids':['a'],'query':'检查','idempotency_key':'same-key'}).json()
                self.assertEqual(result,{'session_id':done,'status':'COMPLETED'})
            for _ in range(2):
                response=client.post(f'/api/audit/sessions/{waiting}/resume')
                self.assertEqual(response.status_code,409);self.assertEqual(response.json()['detail']['code'],'lease_busy')
            self.assertEqual(client.post(f'/api/audit/sessions/{waiting}/followup',json={'query':'再检查'}).status_code,409)
