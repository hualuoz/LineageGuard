from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["critical", "high", "medium", "low"]
Verdict = Literal["block", "manual_review", "pass_with_checks"]


class AssetReference(BaseModel):
    urn: str
    name: str
    type: str = "DATASET"
    hops: int = 1


class ColumnContext(BaseModel):
    name: str
    native_type: str = "unknown"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    glossary_terms: list[str] = Field(default_factory=list)
    downstream_assets: list[AssetReference] = Field(default_factory=list)

    @property
    def sensitive(self) -> bool:
        markers = " ".join(self.tags + self.glossary_terms).lower()
        return any(term in markers for term in ("pii", "sensitive", "confidential", "personal"))


class DatasetContext(BaseModel):
    urn: str
    name: str
    description: str = ""
    owners: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    columns: list[ColumnContext] = Field(default_factory=list)
    downstream_assets: list[AssetReference] = Field(default_factory=list)
    source: str = "fixture"

    def column(self, name: str) -> ColumnContext | None:
        normalized = name.strip('`"').lower()
        return next((column for column in self.columns if column.name.lower() == normalized), None)


class Finding(BaseModel):
    severity: Severity
    code: str
    title: str
    evidence: str
    recommendation: str
    affected_assets: list[AssetReference] = Field(default_factory=list)


class ReviewReport(BaseModel):
    dataset: DatasetContext
    risk_score: int = Field(ge=0, le=100)
    verdict: Verdict
    summary: str
    findings: list[Finding]
    safe_migration_plan: list[str]
    analyzed_statements: int
