"""Phase 2 session command API; no streaming or UI workflow in this phase."""
import asyncio
import uuid
import json
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, Response
from evidence.db import AuditDB
from evidence.agent_harness import Harness
from evidence.harness_schemas import CreateSession, FollowupInput
from evidence.harness_store import Conflict
from evidence.replay import make_bundle, markdown

router=APIRouter(prefix='/api/audit/sessions')
_tasks=set()
async def schedule(harness,id):
    owner=uuid.uuid4().hex
    try: acquired=await asyncio.to_thread(harness.store.acquire,id,owner)
    except KeyError: raise HTTPException(404,detail={'code':'session_not_found','message':'会话不存在。'}) from None
    if not acquired:
        state=await asyncio.to_thread(harness.store.public,id)
        if state['status']=='COMPLETED': return {'session_id':id,'status':'COMPLETED'}
        raise HTTPException(409,detail={'code':'lease_busy','message':'会话正在执行或等待执行权到期。','retry_after':state['retry_after']})
    task=asyncio.create_task(harness.run(id,owner=owner,acquired=True)); _tasks.add(task)
    def done(t):
        _tasks.discard(t)
        if not t.cancelled(): t.exception()
    task.add_done_callback(done)
    return {'session_id':id,'status':'scheduled'}

@router.post('')
async def create(body:CreateSession):
    harness=Harness(await asyncio.to_thread(AuditDB))
    try: id=await asyncio.to_thread(harness.create,body.snapshot_ids,body.query,body.idempotency_key,body.budget.model_dump())
    except (ValueError,Conflict) as e: raise HTTPException(409,detail={'code':'invalid_session','message':str(e)}) from None
    if body.idempotency_key:
        existing=await asyncio.to_thread(harness.store.public,id)
        if existing['status']!='INIT': return {'session_id':id,'status':existing['status']}
    try: return await schedule(harness,id)
    except HTTPException as e:
        if body.idempotency_key and e.status_code==409: return {'session_id':id,'status':'running'}
        raise

@router.get('')
async def list_sessions():
    db=await asyncio.to_thread(AuditDB)
    def read():
        with db.connect() as c:
            return [{'id':r['id'],'status':r['status'],'created_at':r['created_at'],'updated_at':r['updated_at'],'query':json.loads(r['payload']).get('query',''),'bindings':json.loads(r['payload']).get('bindings',[])} for r in c.execute('SELECT * FROM audit_sessions ORDER BY updated_at DESC LIMIT 100')]
    return await asyncio.to_thread(read)

@router.get('/{id}')
async def get(id:str):
    harness=Harness(await asyncio.to_thread(AuditDB))
    try:
        result=await asyncio.to_thread(harness.store.public,id)
        def traces():
            with harness.db.connect() as c:
                return [{'repo':r['repo'],'commit':r['commit_sha'],'tool':r['tool_name'],'status':r['status'],'created_at':r['created_at'],**{k:v for k,v in json.loads(r['payload']).items() if k in ('args','duration_ms','evidence_ids')}} for r in c.execute('SELECT * FROM tool_traces WHERE session_id=? ORDER BY id',(id,))]
        result['traces']=await asyncio.to_thread(traces)
        return result
    except KeyError: raise HTTPException(404,detail={'code':'session_not_found','message':'会话不存在。'}) from None

@router.get('/{id}/stream')
async def stream(id:str,request:Request,after:int=Query(0,ge=0)):
    harness=Harness(await asyncio.to_thread(AuditDB))
    try: await asyncio.to_thread(harness.store.get,id)
    except KeyError: raise HTTPException(404,detail={'code':'session_not_found','message':'会话不存在。'}) from None
    try: cursor=max(after,int(request.headers.get('last-event-id','0')))
    except ValueError: raise HTTPException(400,detail={'code':'invalid_cursor','message':'事件游标无效。'}) from None
    async def events():
        nonlocal cursor
        idle=0
        while not await request.is_disconnected():
            current=await asyncio.to_thread(harness.store.public,id)
            for event in current['events']:
                if event['id']>cursor:
                    cursor=event['id']; yield f"id: {cursor}\nevent: update\ndata: {json.dumps(event,ensure_ascii=False)}\n\n"; idle=0
            if current['status'] in ('COMPLETED','INTERRUPTED','FAILED'):
                yield f"event: terminal\ndata: {json.dumps({'status':current['status']})}\n\n"; break
            if idle>=15: yield ': heartbeat\n\n'; idle=0
            await asyncio.sleep(1); idle+=1
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@router.get('/{id}/evidence/{evidence_id}')
async def evidence(id:str,evidence_id:str):
    db=await asyncio.to_thread(AuditDB)
    def read():
        with db.connect() as c:
            row=c.execute('SELECT e.payload FROM evidence_artifacts e JOIN session_evidence s ON s.evidence_id=e.id WHERE s.session_id=? AND e.id=?',(id,evidence_id)).fetchone()
            return json.loads(row['payload']) if row else None
    result=await asyncio.to_thread(read)
    if result is None: raise HTTPException(404,detail={'code':'evidence_not_found','message':'本会话没有该证据。'})
    return result

@router.get('/{id}/export')
async def export(id:str,format:str=Query('replay',pattern='^(replay|markdown)$')):
    db=await asyncio.to_thread(AuditDB);harness=Harness(db)
    try:
        if format=='markdown':
            bundle=await asyncio.to_thread(make_bundle,db,id); payload=json.loads(bundle['payload_json'])
            content=markdown(payload['session'],payload['evidence']); media='text/markdown; charset=utf-8'; name='report.md'
        else:
            content=json.dumps(await asyncio.to_thread(make_bundle,db,id),ensure_ascii=False);media='application/json';name='replay.json'
        return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="{name}"'})
    except KeyError: raise HTTPException(404,detail={'code':'session_not_found','message':'会话不存在。'}) from None
    except ValueError as e: raise HTTPException(422,detail={'code':'export_invalid','message':str(e)}) from None

@router.post('/{id}/resume')
async def resume(id:str):
    harness=Harness(await asyncio.to_thread(AuditDB))
    return await schedule(harness,id)

@router.post('/{id}/followup')
async def followup(id:str,body:FollowupInput):
    harness=Harness(await asyncio.to_thread(AuditDB))
    try: await asyncio.to_thread(harness.store.followup,id,body.query)
    except KeyError: raise HTTPException(404,detail={'code':'session_not_found','message':'会话不存在。'}) from None
    except Conflict as e: raise HTTPException(409,detail={'code':'session_busy','message':str(e)}) from None
    return await schedule(harness,id)
