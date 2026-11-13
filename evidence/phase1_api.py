"""Direct Phase 1 tools and legacy snapshot adapter, without agent execution."""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from evidence.schemas import Binding, OverviewInput, OutlineInput, ScanInput, SecurityScanInput, LinesInput, IssueInput, ToolResult
from evidence.db import AuditDB
from evidence.github_client import GitHubClient, GitHubError
from evidence.tools import AuditTools

router=APIRouter(prefix='/api/phase1')
class RepoInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    repo: str

@router.post('/snapshots')
async def snapshot(body: RepoInput):
    db=await asyncio.to_thread(AuditDB)
    client=GitHubClient(db=db)
    try: return await client.create_snapshot(body.repo)
    except GitHubError as e: raise HTTPException(422,detail={'code':e.code,'message':e.message}) from None
    finally: await client.close()

@router.post('/import-legacy')
def import_legacy(): return AuditDB().import_legacy()

@router.get('/snapshots/{snapshot_id}')
def snapshot_by_id(snapshot_id:str):
    item=AuditDB().get_snapshot(snapshot_id)
    if not item: raise HTTPException(404,detail={'code':'snapshot_not_found','message':'快照不存在，请先导入旧库或创建快照。'})
    return item

async def dispatch(method,body):
    db=await asyncio.to_thread(AuditDB)
    if not await asyncio.to_thread(db.has_public_binding,body.repo,body.commit):
        raise HTTPException(403,detail={'code':'unregistered_snapshot','message':'仓库和提交未登记为公开快照，请先创建或导入快照。'})
    client=GitHubClient(db=db); tools=AuditTools({'repo':body.repo,'commit':body.commit},client)
    try: return await getattr(tools,method)(body.model_dump())
    finally: await client.close()

@router.post('/overview',response_model=ToolResult)
async def overview(body:OverviewInput): return await dispatch('get_repo_overview_and_tree',body)
@router.post('/outline',response_model=ToolResult)
async def outline(body:OutlineInput): return await dispatch('get_markdown_outline',body)
@router.post('/lines',response_model=ToolResult)
async def lines(body:LinesInput): return await dispatch('read_file_lines',body)
@router.post('/dependencies',response_model=ToolResult)
async def dependencies(body:Binding): return await dispatch('inspect_dependencies_and_env',body)
@router.post('/deployment',response_model=ToolResult)
async def deployment(body:Binding): return await dispatch('inspect_deployment_artifacts',body)
@router.post('/issues',response_model=ToolResult)
async def issues(body:IssueInput): return await dispatch('search_repo_issues_and_risks',body)
@router.post('/architecture',response_model=ToolResult)
async def architecture(body:ScanInput): return await dispatch('analyze_architecture_profile',body)
@router.post('/security',response_model=ToolResult)
async def security(body:SecurityScanInput): return await dispatch('scan_security_and_risk_sinks',body)
