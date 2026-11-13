import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from evidence.app import app
from evidence.config import Settings
from evidence.db import AuditDB
from evidence.github_client import GitHubClient, GitHubError
from evidence.tools import AuditTools
from evidence.schemas import FileEvidence

REPO='test/repo'; SHA='a'*40; B={'repo':REPO,'commit':SHA}
class FakeClient:
    def __init__(self,db,files,issue_data=None):
        self.db=db; self.settings=db.settings; self.files=files; self.issue_data=issue_data or []
    async def close(self): pass
    async def metadata(self,repo): return {'full_name':repo},'now'
    async def tree(self,repo,sha,path=''):
        prefix=path+'/' if path else ''; entries=[]; seen=set()
        for p,text in self.files.items():
            if not p.startswith(prefix): continue
            rest=p[len(prefix):]; name=rest.split('/')[0]
            if name in seen: continue
            seen.add(name); entries.append({'name':name,'type':'tree' if '/' in rest else 'blob','sha':'b'*40,'size':None if '/' in rest else len(text.encode()),'mode':'040000' if '/' in rest else '100644'})
        return {'entries':entries,'truncated':False},'now',True
    async def file(self,repo,sha,path):
        from evidence.github_client import valid_path
        valid_path(path)
        if path not in self.files: raise GitHubError('not_found','文件不存在。')
        text=self.files[path]
        if '\x00' in text: raise GitHubError('binary_file','文件不是 UTF-8 文本。')
        return {'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()},'now',True
    async def issues(self,repo,query,state): return {'items':self.issue_data},False,'now'
    async def comments(self,repo,number): return self.comment_data,False,'now'

class PhaseOne(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.settings=replace(Settings(),data_dir=Path(self.tmp.name));self.db=AuditDB(self.settings)
        self.files={'README.md':'# 标题\n```md\n# 伪标题\n```\n## 子标题\n正文\n','empty':'','wide.txt':'中'*6002+'\n', 'module.py':'def run():\n    pass\n\nclass Demo:\n    pass\n', 'requirements.txt':'requests>=2\nhttpx==0.28.1\n','Dockerfile':'FROM python:3.11\nEXPOSE 8000\n','compose.yaml':'services:\n  api:\n    image: python:3.11\n    ports:\n      - "8000:8000"\n'}
        self.client=FakeClient(self.db,self.files);self.tools=AuditTools(B,self.client)
    async def test_outline_fence_and_original_lines(self):
        r=await self.tools.get_markdown_outline({**B,'path':'README.md'}); self.assertFalse(r.errors)
        self.assertEqual([e.start_line for e in r.facts[0].entries],[1,5]); self.assertEqual(r.evidence[0].source_type,'file_outline'); self.assertEqual(r.evidence[0].evidence_id,r.facts[0].evidence_id)
        self.assertIn('子标题',r.evidence[0].text)
    async def test_ast_and_line_block(self):
        r=await self.tools.get_markdown_outline({**B,'path':'module.py'});self.assertEqual(r.facts[0].kind,'python_ast');self.assertEqual(r.facts[0].entries[0].end_line,2)
        r=await self.tools.get_markdown_outline({**B,'path':'wide.txt'});self.assertEqual(r.facts[0].kind,'line_blocks')
    async def test_single_line_empty_and_character_truncation(self):
        r=await self.tools.read_file_lines({**B,'path':'README.md','start_line':5,'end_line':5});self.assertEqual(r.evidence[0].start_line,5);self.assertEqual(r.evidence[0].end_line,5)
        r=await self.tools.read_file_lines({**B,'path':'empty','start_line':1,'end_line':1});self.assertIsNone(r.evidence[0].start_line);self.assertNotIn('#L',r.evidence[0].source_url)
        r=await self.tools.read_file_lines({**B,'path':'wide.txt','start_line':1,'end_line':1});self.assertEqual(len(r.evidence[0].text),6000);self.assertTrue(r.evidence[0].partial_line)
    async def test_120_line_boundary(self):
        self.files['long']='x\n'*200
        blocked=await self.tools.read_file_lines({**B,'path':'long','start_line':1,'end_line':200}); self.assertEqual(blocked.errors[0].code,'outline_required')
        await self.tools.get_markdown_outline({**B,'path':'long'})
        r=await self.tools.read_file_lines({**B,'path':'long','start_line':1,'end_line':200});self.assertEqual(r.evidence[0].end_line,120);self.assertTrue(r.coverage.truncated)
    async def test_invalid_path_binding_binary_and_malformed(self):
        for path in ('../x','https://github.com/a/b','/x'):
            r=await self.tools.read_file_lines({**B,'path':path,'start_line':1,'end_line':1});self.assertTrue(r.errors)
        r=await self.tools.read_file_lines({**B,'repo':'other/repo','path':'README.md','start_line':1,'end_line':1});self.assertEqual(r.errors[0].code,'binding_mismatch')
        self.files['binary']='\0xx';r=await self.tools.read_file_lines({**B,'path':'binary','start_line':1,'end_line':1});self.assertEqual(r.errors[0].code,'binary_file')
        r=await self.tools.read_file_lines({**B,'path':'README.md','start_line':0,'end_line':1});self.assertEqual(r.errors[0].code,'invalid_input')
    async def test_dependencies_and_deployment_have_linked_lines(self):
        r=await self.tools.inspect_dependencies_and_env(B); self.assertTrue(any(getattr(f,'value','').startswith('requests') for f in r.facts));self.assertTrue(r.evidence);self.assertFalse(r.coverage.complete)
        r=await self.tools.inspect_deployment_artifacts(B); values=[getattr(f,'value','') for f in r.facts];self.assertTrue(any('FROM python:3.11' in x for x in values));self.assertTrue(any('api:' in x for x in values));self.assertTrue(r.evidence)
    async def test_structured_config_values(self):
        self.files['.python-version']='3.11\n'
        self.files['package.json']='{\n "engines": {\n   "node": ">=20"\n },\n "dependencies": {"foo": "^1"}\n}\n'
        self.files['compose.yaml']='services:\n  api:\n    image: python:3.11\n    ports:\n      - "8000:8000"\n    environment:\n      MODEL_URL: http://host\n'
        deps=await self.tools.inspect_dependencies_and_env(B)
        values={(getattr(f,'key',None),getattr(f,'value',None)) for f in deps.facts}
        self.assertIn(('python.version','3.11'),values);self.assertIn(('engines.node','>=20'),values)
        deploy=await self.tools.inspect_deployment_artifacts(B)
        values={(getattr(f,'key',None),getattr(f,'value',None)) for f in deploy.facts}
        self.assertIn(('services.api.ports','8000:8000'),values);self.assertIn(('services.api.environment.MODEL_URL','http://host'),values);self.assertIn(('docker.FROM','python:3.11'),values);self.assertIn(('docker.EXPOSE','8000'),values)
        for fact in deploy.facts:
            if fact.kind=='config_value': self.assertTrue(any(e.evidence_id==fact.evidence_id and e.start_line==fact.line for e in deploy.evidence))
    async def test_config_uses_correct_toml_section_and_compact_json(self):
        self.files={'pyproject.toml':'# requires-python = ">=3.8"\n[other]\nrequires-python = ">=3.9"\n[project]\nrequires-python = ">=3.12"\n', 'package.json':'{"engines":{"node":">=20"},"dependencies":{"openai":"^4"}}\n'}
        self.client.files=self.files
        result=await self.tools.inspect_dependencies_and_env(B)
        configs=[x for x in result.facts if x.kind=='config_value']
        python=next(x for x in configs if x.key=='project.requires-python')
        self.assertEqual((python.value,python.line),('>=3.12',5))
        node=next(x for x in configs if x.key=='engines.node'); self.assertEqual((node.value,node.line),('>=20',1))
        self.assertEqual(next(x for x in configs if x.key=='dependencies.openai').value,'^4')
        ev=next(e for e in result.evidence if e.evidence_id==python.evidence_id)
        self.assertIn('>=3.12',ev.text);self.assertNotIn('>=3.8',ev.text)
    async def test_long_line_cannot_produce_unsupported_value(self):
        self.files={'package.json':'{"padding":"' + 'x'*6100 + '","engines":{"node":">=20"}}'}; self.client.files=self.files
        result=await self.tools.inspect_dependencies_and_env(B)
        self.assertFalse(any(getattr(x,'key','')=='engines.node' for x in result.facts))
        self.assertTrue(any('未返回结构化值' in n for n in result.coverage.notes))
    async def test_no_heading_markdown_uses_blocks(self):
        self.files['plain.md']='plain\n'*200
        r=await self.tools.get_markdown_outline({**B,'path':'plain.md'})
        self.assertEqual(r.facts[0].kind,'line_blocks');self.assertEqual(len(r.facts[0].entries),4)
    async def test_overview_two_levels_and_path(self):
        self.files['src/nested/code.py']='x'
        r=await self.tools.get_repo_overview_and_tree(B)
        self.assertTrue(any(getattr(f,'path',None)=='src' for f in r.facts))
        r=await self.tools.get_repo_overview_and_tree({**B,'path':'src'})
        self.assertTrue(any(getattr(f,'path',None)=='src/nested' for f in r.facts))
    async def test_overview_tree_has_durable_evidence(self):
        r=await self.tools.get_repo_overview_and_tree(B);self.assertEqual(r.evidence[0].source_type,'repo_metadata');self.assertTrue(any(x.source_type=='repo_tree' for x in r.evidence));self.assertIsNotNone(self.db.get_evidence(r.evidence[0].evidence_id))
    async def test_issues_mismatch_and_comment_binding(self):
        good={'number':1,'id':11,'updated_at':'now','body':'problem','title':'bug','state':'open','comments':1,'repository_url':'https://api.github.com/repos/test/repo','html_url':'https://github.com/test/repo/issues/1'}
        bad={**good,'number':2,'id':12,'repository_url':'https://api.github.com/repos/other/repo','html_url':'https://github.com/other/repo/issues/2'}
        self.client.issue_data=[good,bad];self.client.comment_data=[{'id':99,'updated_at':'now','body':'x','issue_url':'https://api.github.com/repos/other/repo/issues/1','html_url':'https://github.com/other/repo/issues/1#issuecomment-99'}]
        r=await self.tools.search_repo_issues_and_risks({**B,'query_keywords':'docker','state':'open'})
        self.assertEqual(len(r.evidence),1);self.assertEqual({e.code for e in r.errors},{'issue_repository_mismatch','comment_repository_mismatch'});self.assertEqual(r.evidence[0].observed_against_commit,SHA)
    async def test_issue_content_limit_is_explicit(self):
        self.client.issue_data=[{'number':1,'id':11,'updated_at':'now','body':'x'*6001,'title':'bug','state':'open','comments':0,'repository_url':'https://api.github.com/repos/test/repo','html_url':'https://github.com/test/repo/issues/1'}]
        r=await self.tools.search_repo_issues_and_risks({**B,'query_keywords':'docker','state':'open'})
        self.assertTrue(r.coverage.truncated);self.assertFalse(r.evidence);self.assertTrue(any('预算' in x for x in r.coverage.notes))
    async def test_issue_reobservation_and_commit_identity(self):
        item={'number':1,'id':11,'updated_at':'now','body':'problem','title':'bug','state':'open','comments':0,'repository_url':'https://api.github.com/repos/test/repo','html_url':'https://github.com/test/repo/issues/1'}
        self.client.issue_data=[item]
        a=await self.tools.search_repo_issues_and_risks({**B,'query_keywords':'docker','state':'open'})
        async def later(repo,query,state): return {'items':[item]},False,'later'
        self.client.issues=later
        b=await self.tools.search_repo_issues_and_risks({**B,'query_keywords':'docker','state':'open'})
        self.assertEqual(a.evidence[0],b.evidence[0]); self.assertEqual(b.evidence[0].fetched_at,'now')
        other=AuditTools({'repo':REPO,'commit':'c'*40},self.client)
        c=await other.search_repo_issues_and_risks({'repo':REPO,'commit':'c'*40,'query_keywords':'docker','state':'open'})
        self.assertNotEqual(a.evidence[0].evidence_id,c.evidence[0].evidence_id)
    async def test_malformed_upstream_is_typed_error(self):
        self.client.issue_data=[None];r=await self.tools.search_repo_issues_and_risks({**B,'query_keywords':'x','state':'open'});self.assertEqual(r.errors[0].code,'invalid_response')
    async def test_concurrent_evidence_write_is_idempotent_and_rejects_conflict(self):
        r=await self.tools.read_file_lines({**B,'path':'README.md','start_line':1,'end_line':1})
        ev=r.evidence[0].model_copy(update={'evidence_id':'ev_concurrent'})
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda _:self.db.save_evidence(ev),range(12)))
        self.assertEqual(self.db.get_evidence('ev_concurrent')['text'],ev.text)
        with self.assertRaises(ValueError): self.db.save_evidence(ev.model_copy(update={'text':'different'}))
    async def test_evidence_conflict_rejected(self):
        r=await self.tools.read_file_lines({**B,'path':'README.md','start_line':1,'end_line':1});ev=r.evidence[0]; altered=ev.model_copy(update={'text':'tampered'})
        with self.assertRaises(ValueError): self.db.save_evidence(altered)

class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.settings=replace(Settings(),data_dir=Path(self.tmp.name));self.db=AuditDB(self.settings)
    async def test_private_snapshot_rejected_before_registration(self):
        client=GitHubClient(self.db,self.settings,transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'private':True,'full_name':'test/repo','default_branch':'main'})))
        try:
            with self.assertRaises(GitHubError) as ctx: await client.create_snapshot(REPO)
            self.assertEqual(ctx.exception.code,'private_repository');self.assertFalse(self.db.has_public_binding(REPO,SHA))
        finally: await client.close()
    async def test_rate_limit_and_keyword_injection(self):
        client=GitHubClient(self.db,self.settings,transport=httpx.MockTransport(lambda req:httpx.Response(403,headers={'X-RateLimit-Remaining':'0'})))
        try:
            with self.assertRaises(GitHubError) as ctx: await client.request('/repos/test/repo')
            self.assertEqual(ctx.exception.code,'rate_limited')
            for word in ('repo:other/repo','docker OR repo:other/repo','state:closed'):
                with self.assertRaises(GitHubError) as ctx: await client.issues(REPO,word,'open')
                self.assertEqual(ctx.exception.code,'invalid_keywords')
        finally: await client.close()
    async def test_corrupt_cached_blob_is_rejected(self):
        self.db.put_cache(REPO,SHA,'tree','',{'entries':[{'name':'x','type':'blob','sha':'b'*40,'size':1,'mode':'100644'}],'truncated':False},'now')
        self.db.put_cache(REPO,SHA,'blob','x',{'text':'x','sha256':'wrong'},'now')
        client=GitHubClient(self.db,self.settings,transport=httpx.MockTransport(lambda req: self.fail('cache must not hit network')))
        try:
            with self.assertRaises(GitHubError) as ctx: await client.file(REPO,SHA,'x')
            self.assertEqual(ctx.exception.code,'cache_corrupt')
        finally: await client.close()
    async def test_tree_truncation_does_not_claim_missing(self):
        entries={'tree':[], 'truncated':True}
        client=GitHubClient(self.db,self.settings,transport=httpx.MockTransport(lambda req:httpx.Response(200,json=entries)))
        try:
            with self.assertRaises(GitHubError) as ctx: await client.file(REPO,SHA,'missing')
            self.assertEqual(ctx.exception.code,'tree_incomplete')
        finally: await client.close()
    async def test_retries_are_bounded(self):
        count=0
        def handler(req):
            nonlocal count
            count+=1
            return httpx.Response(503 if count<3 else 200,json={'ok':True})
        client=GitHubClient(self.db,self.settings,transport=httpx.MockTransport(handler))
        try:
            with patch('evidence.github_client.asyncio.sleep',return_value=None): data,_=await client.request('/repos/test/repo')
            self.assertTrue(data['ok']);self.assertEqual(count,3)
        finally: await client.close()
    async def test_issue_pagination_and_incomplete(self):
        client=GitHubClient(self.db,self.settings,transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'items':[],'total_count':1,'incomplete_results':False},headers={'Link':'<https://api.github.com/a?page=2>; rel="next"'})))
        try: _,partial,_=await client.issues(REPO,'docker','open');self.assertTrue(partial)
        finally: await client.close()

class APIBindingTests(unittest.TestCase):
    def test_unregistered_commit_and_other_repo_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            db=AuditDB(replace(Settings(),data_dir=Path(d)))
            db.put_snapshot({'id':'registered','repo':REPO,'sha':SHA,'created_at':'now'})
            client=TestClient(app)
            with patch('evidence.phase1_api.AuditDB',return_value=db), patch('evidence.phase1_api.GitHubClient') as gh:
                for repo,sha in ((REPO,'b'*40),('other/repo',SHA),('private/repo',SHA)):
                    response=client.post('/api/phase1/lines',json={'repo':repo,'commit':sha,'path':'README.md','start_line':1,'end_line':1})
                    self.assertEqual(response.status_code,403);self.assertEqual(response.json()['detail']['code'],'unregistered_snapshot')
                gh.assert_not_called()

class MigrationTests(unittest.TestCase):
    def test_backup_import_restart_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            settings=replace(Settings(),data_dir=Path(d)); old=sqlite3.connect(settings.legacy_path)
            old.executescript('CREATE TABLE snapshots(id TEXT,repo TEXT,sha TEXT,created_at TEXT); CREATE TABLE cache(repo TEXT,sha TEXT,kind TEXT,path TEXT,payload TEXT,fetched_at TEXT);')
            blob={'text':'hello','sha256':hashlib.sha256(b'hello').hexdigest()}
            old.execute('INSERT INTO snapshots VALUES (?,?,?,?)',('id',REPO,SHA,'now'));old.execute('INSERT INTO cache VALUES (?,?,?,?,?,?)',(REPO,SHA,'blob','README.md',json.dumps(blob),'now'));old.commit();old.close()
            db=AuditDB(settings);a=db.import_legacy();b=db.import_legacy();self.assertEqual(a['cache'],1);self.assertTrue(Path(a['backup']).exists());self.assertNotEqual(a['backup'],b['backup'])
            code='from evidence.config import Settings; from evidence.db import AuditDB; from dataclasses import replace; from pathlib import Path; import sys; d=AuditDB(replace(Settings(),data_dir=Path(sys.argv[1]))); assert d.get_cache("test/repo","'+SHA+'","blob","README.md")[0]["text"]=="hello"; assert d.get_snapshot("id")'
            subprocess.run([sys.executable,'-c',code,d],check=True)
            with db.connect() as conn: self.assertEqual(conn.execute('PRAGMA journal_mode').fetchone()[0],'wal');self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],4)
    def test_parallel_initialization_and_import(self):
        with tempfile.TemporaryDirectory() as d:
            settings=replace(Settings(),data_dir=Path(d));old=sqlite3.connect(settings.legacy_path)
            old.executescript('CREATE TABLE snapshots(id TEXT,repo TEXT,sha TEXT,created_at TEXT); CREATE TABLE cache(repo TEXT,sha TEXT,kind TEXT,path TEXT,payload TEXT,fetched_at TEXT);')
            old.execute('INSERT INTO snapshots VALUES (?,?,?,?)',('id',REPO,SHA,'now'));old.commit();old.close()
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:AuditDB(settings).import_legacy(),range(4)))
            self.assertEqual(len(results),4);self.assertTrue(all(x['snapshots']==1 for x in results))
            self.assertEqual(AuditDB(settings).get_snapshot('id')['repo'],REPO)
    def test_conflict_rolls_back_import(self):
        with tempfile.TemporaryDirectory() as d:
            settings=replace(Settings(),data_dir=Path(d)); old=sqlite3.connect(settings.legacy_path)
            old.executescript('CREATE TABLE snapshots(id TEXT,repo TEXT,sha TEXT,created_at TEXT); CREATE TABLE cache(repo TEXT,sha TEXT,kind TEXT,path TEXT,payload TEXT,fetched_at TEXT);')
            old.execute('INSERT INTO snapshots VALUES (?,?,?,?)',('id',REPO,SHA,'now'));old.commit();old.close()
            db=AuditDB(settings);db.put_snapshot({'id':'id','repo':'other/repo','sha':SHA,'created_at':'now'})
            with self.assertRaises(ValueError): db.import_legacy()
            self.assertEqual(db.get_snapshot('id')['repo'],'other/repo')
    def test_bad_hash_does_not_import(self):
        with tempfile.TemporaryDirectory() as d:
            settings=replace(Settings(),data_dir=Path(d));old=sqlite3.connect(settings.legacy_path)
            old.executescript('CREATE TABLE snapshots(id TEXT,repo TEXT,sha TEXT,created_at TEXT); CREATE TABLE cache(repo TEXT,sha TEXT,kind TEXT,path TEXT,payload TEXT,fetched_at TEXT);')
            old.execute('INSERT INTO snapshots VALUES (?,?,?,?)',('id',REPO,SHA,'now'));old.execute('INSERT INTO cache VALUES (?,?,?,?,?,?)',(REPO,SHA,'blob','x',json.dumps({'text':'x','sha256':'wrong'}),'now'));old.commit();old.close()
            db=AuditDB(settings)
            with self.assertRaises(ValueError):db.import_legacy()
            self.assertIsNone(db.get_snapshot('id'));self.assertEqual(len(list(Path(d).glob('*.backup'))),1)

if __name__=='__main__': unittest.main()
