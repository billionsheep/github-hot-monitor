import asyncio, json, os, subprocess, sys, tempfile
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT), str(ROOT/'tests')]
from evidence.config import Settings
from evidence.db import AuditDB
from evidence.agent_harness import Harness
from test_harness import FixtureModel, FixtureProvider, SHA_A, SHA_B

def database(path): return AuditDB(replace(Settings(), data_dir=Path(path)))
async def child(path, sid, mode):
    db=database(path)
    async def hook(name, details):
        if mode=='crash' and name=='tool_committed': os._exit(77)
    h=Harness(db,FixtureModel(),FixtureProvider(db),hook)
    ok=await h.run(sid)
    print(json.dumps({'ran':ok,'status':h.store.public(sid)['status']}))

if len(sys.argv)>1:
    asyncio.run(child(*sys.argv[1:]));sys.exit()
with tempfile.TemporaryDirectory(prefix='repoaudit-crash-') as path:
    db=database(path)
    for sid,repo,sha in [('a','test/alpha',SHA_A),('b','test/beta',SHA_B)]:
        db.put_snapshot({'id':sid,'repo':repo,'sha':sha,'created_at':'fixture'})
    h=Harness(db,FixtureModel(),FixtureProvider(db));sid=h.create(['a','b'],'比较模型配置')
    proc=subprocess.run([sys.executable,__file__,path,sid,'crash'],capture_output=True,text=True)
    assert proc.returncode==77, (proc.returncode, proc.stderr)
    with db.connect() as c:
        before=[dict(r) for r in c.execute('SELECT * FROM tool_receipts WHERE session_id=?',(sid,))]
    assert len(before)==1, before
    held=subprocess.run([sys.executable,__file__,path,sid,'resume'],capture_output=True,text=True)
    assert held.returncode==0, held.stderr
    assert json.loads(held.stdout)['ran'] is False, held.stdout
    # Simulate expiration of the dead process lease, avoiding a three-minute test wait.
    with db.connect() as c: c.execute('UPDATE audit_sessions SET lease_until=? WHERE id=?',('0',sid))
    recovered=subprocess.run([sys.executable,__file__,path,sid,'resume'],capture_output=True,text=True)
    assert recovered.returncode==0, recovered.stderr
    out=json.loads(recovered.stdout);assert out=={'ran':True,'status':'COMPLETED'},out
    with db.connect() as c:
        rows=[dict(r) for r in c.execute('SELECT * FROM tool_receipts WHERE session_id=?',(sid,))]
        assert sum(r['call_id']==before[0]['call_id'] for r in rows)==1
    print(json.dumps({'hard_exit_code':77,'committed_before_exit':1,'blocked_while_lease_alive':True,'recovered_after_expiry':True,'committed_call_not_duplicated':True,'final_receipts':len(rows)},ensure_ascii=False))
