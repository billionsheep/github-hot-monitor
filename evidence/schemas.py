"""Strict tool contracts: file and issue evidence have distinct provenance."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Binding(StrictModel):
    repo: str
    commit: str = Field(pattern=r'^[0-9a-f]{40}$')

class OverviewInput(Binding):
    path: str = Field(default='', max_length=500)

class PathInput(Binding):
    path: str = Field(min_length=1, max_length=500)

class OutlineInput(PathInput):
    symbol_or_param_hint: str | None = Field(default=None,max_length=200)

class ScanInput(Binding):
    path_prefix: str = Field(default='',max_length=500)

class SecurityScanInput(ScanInput):
    mode: Literal['all','exec_sinks','env_and_network','prompt_injection'] = 'all'

class LinesInput(PathInput):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    @model_validator(mode='after')
    def ordered(self):
        if self.end_line < self.start_line: raise ValueError('end_line must be >= start_line')
        return self

class IssueInput(Binding):
    query_keywords: str = Field(min_length=1, max_length=100)
    state: Literal['open','closed','all'] = 'open'

class FileEvidence(StrictModel):
    source_type: Literal['file_lines'] = 'file_lines'
    evidence_id: str
    repo: str
    commit: str
    path: str
    start_line: int | None
    end_line: int | None
    text: str
    content_sha256: str
    fragment_sha256: str
    source_url: str
    fetched_at: str
    partial_line: bool

class IssueEvidence(StrictModel):
    source_type: Literal['issue','issue_comment']
    evidence_id: str
    repo: str
    observed_against_commit: str
    issue_number: int
    item_id: int
    updated_at: str
    fetched_at: str
    body: str
    body_sha256: str
    source_url: str

class TreeEvidence(StrictModel):
    source_type: Literal['repo_tree'] = 'repo_tree'
    evidence_id: str
    repo: str
    commit: str
    path: str
    text: str
    tree_sha256: str
    source_url: str
    fetched_at: str

class OutlineEvidence(StrictModel):
    source_type: Literal['file_outline'] = 'file_outline'
    evidence_id: str
    repo: str
    commit: str
    path: str
    text: str
    content_sha256: str
    index_sha256: str
    source_url: str
    fetched_at: str

class MetadataEvidence(StrictModel):
    source_type: Literal['repo_metadata'] = 'repo_metadata'
    evidence_id: str
    repo: str
    observed_against_commit: str
    text: str
    metadata_sha256: str
    source_url: str
    fetched_at: str

class DerivedEvidence(StrictModel):
    source_type: Literal['arch_profile','security_scan']
    evidence_id: str
    repo: str
    commit: str
    path_prefix: str
    rule_version: str
    artifact_sha256: str
    references: list[str]
    text: str
    source_url: str
    fetched_at: str

Evidence = Annotated[FileEvidence | IssueEvidence | TreeEvidence | OutlineEvidence | MetadataEvidence | DerivedEvidence, Field(discriminator='source_type')]

class TreeItem(StrictModel):
    name: str
    type: str
    sha: str
    size: int | None = None
    mode: str | None = None

class RepoMetadata(StrictModel):
    full_name: str | None = None
    description: str | None = None
    stargazers_count: int | None = None
    forks_count: int | None = None
    language: str | None = None
    license_spdx: str | None = None
    pushed_at: str | None = None
    open_issues_count: int | None = None
    default_branch: str | None = None

class OutlineEntry(StrictModel):
    start_line: int
    end_line: int
    title: str | None = None
    level: int | None = None
    kind: str | None = None
    evidence_id: str | None = None
    parameters: list[dict] | None = None
    calls: list[dict] | None = None
    aliases: list[dict] | None = None
    calls_truncated: bool | None = None
    symbols: list[str] | None = None

class MetadataFact(StrictModel):
    kind: Literal['metadata']
    observed_at: str
    data: RepoMetadata
    evidence_id: str

class TreeFact(StrictModel):
    kind: Literal['tree']
    path: str
    entries: list[TreeItem]
    fetched_at: str
    evidence_id: str

class OutlineFact(StrictModel):
    kind: Literal['markdown_headings','python_ast','line_blocks']
    path: str
    total_lines: int
    entries: list[OutlineEntry]
    content_sha256: str
    evidence_id: str

class EmptyFact(StrictModel):
    kind: Literal['empty_file']
    value: bool

class ParseFact(StrictModel):
    kind: Literal['file_parse']
    path: str
    format: str
    status: Literal['parsed','parse_error','dynamic_not_executed','line_index_only']
    line_count: int
    parsed_type: str | None = None

class LineFact(StrictModel):
    kind: Literal['declaration_line','deployment_line']
    path: str
    line: int
    value: str
    evidence_id: str

class ConfigFact(StrictModel):
    kind: Literal['config_value']
    path: str
    key: str
    value: str
    line: int
    evidence_id: str

class CommunityFact(StrictModel):
    kind: Literal['community_report']
    issue_number: int
    title: str
    state: str
    evidence_id: str

class DerivedFact(StrictModel):
    kind: Literal['arch_profile','security_scan']
    evidence_id: str

Fact = Annotated[MetadataFact | TreeFact | OutlineFact | EmptyFact | ParseFact | LineFact | ConfigFact | CommunityFact | DerivedFact, Field(discriminator='kind')]

class Coverage(StrictModel):
    complete: bool
    truncated: bool = False
    notes: list[str] = Field(default_factory=list)
    inspected: list[str] = Field(default_factory=list)
    continuation: str | None = None

class ToolError(StrictModel):
    code: str
    message: str

class ToolResult(StrictModel):
    tool: str
    repo: str
    commit: str
    facts: list[Fact] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    coverage: Coverage
    errors: list[ToolError] = Field(default_factory=list)
    cache_hit: bool = False
