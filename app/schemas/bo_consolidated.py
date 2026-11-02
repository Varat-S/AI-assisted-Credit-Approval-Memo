"""Versioned consolidated BO contracts. Legacy contracts remain unchanged."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.agentic import ConclusionClaim

TITLES = ('Corporate Structure & Debt Obligations', 'Management',
          'Competitive Position', 'Refinancing History', 'Industry')

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class QuotedValue(Strict):
    parameter_result_id: str
    value: float
    unit: str | None = None
    period: str | None = None
    denominator: str | None = None

class PointAnalysis(Strict):
    company_evidence: str = Field(min_length=1)
    revenue_or_cost_mechanism: str = Field(min_length=1)
    competitive_and_credit_implication: str = Field(min_length=1)

class Point(ConclusionClaim):
    hypothesis_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    claim_type: Literal['fact', 'calculated_fact', 'management_claim', 'inference', 'assumption']
    section: str
    quoted_values: list[QuotedValue] = Field(default_factory=list)
    dimension: Literal['revenue', 'cost', 'advantage', 'vulnerability', 'mitigant', 'uncertainty']
    counterevidence: list[str] = Field(default_factory=list)
    analysis: PointAnalysis | None = None

class Selection(Strict):
    hypothesis_id: str
    disposition: Literal['selected', 'incorporated', 'audit_only']
    reason: str = Field(min_length=1)
    point_id: str | None

class CompetitiveSynthesis(Strict):
    schema_version: Literal['bo-competitive-1.0', 'bo-competitive-1.1']
    overall_assessment: Point
    key_drivers: list[Point]
    selections: list[Selection]
    coverage_gaps: list[str]
    residual_uncertainty: list[str]
    completeness: Literal['complete', 'incomplete']
    human_review_required: bool

    @model_validator(mode='after')
    def depth(self):
        if self.schema_version == 'bo-competitive-1.1':
            if any(p.analysis is None or any(not v.strip() for v in p.analysis.model_dump().values())
                   for p in self.key_drivers):
                raise ValueError('Each v1.1 selected point needs evidence, mechanism and credit analysis')
        return self

class Source(Strict):
    stage: str
    sha256: str
    case_id: str
    analysis_run_id: str
    evidence_snapshot_version: int

class CopyItem(Strict):
    source_stage: str
    field_path: list[str]
    content_hash: str
    content: Any
    origin: Literal['deterministic_copy'] = 'deterministic_copy'

class Section(Strict):
    title: str
    status: Literal['complete', 'incomplete', 'missing']
    items: list[CopyItem] = Field(default_factory=list)
    synthesis: CompetitiveSynthesis | None = None
    limitations: list[str] = Field(default_factory=list)

class ConsolidatedBO(Strict):
    schema_id: Literal['consolidated-business-overview']
    schema_version: Literal['1.0']
    case_id: str
    analysis_run_id: str
    evidence_snapshot_version: int
    sources: list[Source]
    evidence_sources: list[dict[str, Any]]
    sections: list[Section]
    audit_stage: str
    governance: dict[str, Any]
    challenge: dict[str, Any] | None
    execution_mode: str
    @model_validator(mode='after')
    def ordered(self):
        if tuple(s.title for s in self.sections) != TITLES:
            raise ValueError('Exactly five ordered sections required')
        for source in self.sources:
            if (source.case_id, source.analysis_run_id, source.evidence_snapshot_version) != (
                    self.case_id, self.analysis_run_id, self.evidence_snapshot_version):
                raise ValueError('Cross-run source forbidden')
        return self
