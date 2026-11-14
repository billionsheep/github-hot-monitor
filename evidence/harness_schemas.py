"""Phase 2 public and model contracts."""
from typing import Literal
from pydantic import Field, model_validator
from evidence.schemas import StrictModel

class Criterion(StrictModel):
    id: str = Field(min_length=1,max_length=60,pattern=r'^[A-Za-z0-9_-]+$')
    title: str = Field(min_length=1,max_length=300)

class CriteriaPlan(StrictModel):
    criteria: list[Criterion] = Field(min_length=1,max_length=8)
    @model_validator(mode='after')
    def unique(self):
        if len({x.id for x in self.criteria})!=len(self.criteria): raise ValueError('duplicate criteria')
        return self

class Citation(StrictModel):
    evidence_id: str = Field(min_length=1,max_length=100)
    quote: str = Field(min_length=1,max_length=6000)

class Verdict(StrictModel):
    criterion_id: str
    repo: str
    commit: str = Field(pattern=r'^[0-9a-f]{40}$')
    status: Literal['PASS','RISK','FAIL','UNVERIFIED']
    summary: str = Field(max_length=1500)
    citations: list[Citation] = Field(max_length=8)
    verification_basis: Literal['declaration','static_config','community_report','insufficient']
    runtime_validation_required: bool
    next_step: str = Field(max_length=1000)
    support_relation: Literal['supports','contradicts','partial','insufficient','unknown'] | None = None
    gap_reason: str | None = Field(default=None,max_length=1000)
    status_calibrated: bool | None = None
    original_status: Literal['PASS','RISK','FAIL','UNVERIFIED'] | None = None

class IntegrationBlueprint(StrictModel):
    format: Literal['python','json','env']
    content: str = Field(min_length=1,max_length=8000)
    applicability: str = Field(min_length=1,max_length=1000)
    verification_steps: list[str] = Field(min_length=1,max_length=8)
    citations: list[Citation] = Field(min_length=1,max_length=8)

class SecurityReview(StrictModel):
    evidence_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: str = Field(min_length=1,max_length=6000)
    explanation: str = Field(min_length=10,max_length=1000)

class SubReport(StrictModel):
    rows: list[Verdict] = Field(max_length=8)
    integration_blueprint: IntegrationBlueprint | None = None
    security_reviews: list[SecurityReview] = Field(default_factory=list,max_length=40)

class ArchitectureGraph(StrictModel):
    repo: str
    commit: str
    artifact_id: str
    edges: list[dict] = Field(max_length=40)

class SecurityFindings(StrictModel):
    repo: str
    commit: str
    artifact_id: str
    findings: list[dict] = Field(max_length=40)

class AnalysisMetrics(StrictModel):
    repo: str
    commit: str
    artifact_id: str
    scope: dict

class BlueprintGroup(StrictModel):
    repo: str
    commit: str
    blueprint: IntegrationBlueprint

class V3ReportExtensions(StrictModel):
    architecture_graph: list[ArchitectureGraph] = Field(default_factory=list,max_length=24)
    security_findings: list[SecurityFindings] = Field(default_factory=list,max_length=24)
    analysis_metrics: list[AnalysisMetrics] = Field(default_factory=list,max_length=24)
    integration_blueprint: list[BlueprintGroup] = Field(default_factory=list,max_length=24)
    analysis_gaps: list[str] = Field(default_factory=list,max_length=100)

class LeadSummary(StrictModel):
    summary: str = Field(max_length=2000)

class TurnBudget(StrictModel):
    model_requests: int = Field(default=20,ge=1,le=20)
    tool_calls: int = Field(default=24,ge=1,le=24)
    input_tokens: int = Field(default=60000,ge=1000,le=60000)
    output_tokens: int = Field(default=16384,ge=2048,le=16384)

class CreateSession(StrictModel):
    snapshot_ids: list[str] = Field(min_length=1,max_length=3)
    query: str = Field(min_length=1,max_length=1500)
    budget: TurnBudget = Field(default_factory=TurnBudget)
    idempotency_key: str | None = Field(default=None,max_length=100)
    workflow_mode: Literal['deploy_readiness','arch_research','sec_sentinel'] = 'deploy_readiness'
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.snapshot_ids))!=len(self.snapshot_ids): raise ValueError('duplicate snapshot')
        return self

class FollowupInput(StrictModel):
    query: str = Field(min_length=1,max_length=1500)
