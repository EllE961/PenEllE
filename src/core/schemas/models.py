"""Pydantic models matching JSON schemas."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SchemaVersion(str):
    """Schema version constant."""

    VERSION = "1.0"


# Enums
class RunStatus(str, Enum):
    """Run status values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvidenceType(str, Enum):
    """Evidence type values."""

    STATISTIC = "statistic"
    QUOTE = "quote"
    METHOD = "method"
    CASESTUDY = "casestudy"
    TABLE = "table"
    FIGURE = "figure"


class SectionType(str, Enum):
    """Section types for drafts."""

    INTRODUCTION = "introduction"
    METHODOLOGY = "methodology"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    ABSTRACT = "abstract"
    CUSTOM = "custom"


class ClaimType(str, Enum):
    """Claim type values."""

    FACTUAL = "factual"
    INTERPRETIVE = "interpretive"
    EVALUATIVE = "evaluative"
    CAUSAL = "causal"
    PREDICTIVE = "predictive"


class VerificationStatus(str, Enum):
    """Claim verification status."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"
    RETRACTED = "retracted"


class StylePack(str, Enum):
    """Writing style templates."""

    ACADEMIC_REPORT = "academic_report"
    ESSAY = "essay"
    POLICY_BRIEF = "policy_brief"
    NEWS_ARTICLE = "news_article"


class CitationStyle(str, Enum):
    """Citation styles."""

    APA = "apa"
    MLA = "mla"
    CHICAGO = "chicago"
    HARVARD = "harvard"
    IEEE = "ieee"
    VANCOUVER = "vancouver"


# Base models
class BaseSchemaModel(BaseModel):
    """Base model with schema version."""

    schema_version: Literal["1.0"] = Field(default=SchemaVersion.VERSION)

    model_config = ConfigDict(json_schema_extra={"examples": []})


class CSLAuthor(BaseModel):
    """CSL-JSON author format."""

    family: Optional[str] = None
    given: Optional[str] = None


class CSLDate(BaseModel):
    """CSL-JSON date format."""

    date_parts: Optional[List[List[int]]] = Field(None, alias="date-parts")


class CSLJSON(BaseModel):
    """CSL-JSON bibliographic data."""

    type: str
    id: Optional[str] = None
    title: str
    author: Optional[List[CSLAuthor]] = None
    issued: Optional[CSLDate] = None
    container_title: Optional[str] = Field(None, alias="container-title")
    volume: Optional[str] = None
    issue: Optional[str] = None
    page: Optional[str] = None
    DOI: Optional[str] = None
    URL: Optional[str] = None
    abstract: Optional[str] = None

    model_config = ConfigDict()


# Schema models
class Source(BaseSchemaModel):
    """Literature source model."""

    id: UUID
    fingerprint: str = Field(..., pattern="^[a-f0-9]{64}$")
    csl_json: CSLJSON
    quality_score: Optional[float] = Field(None, ge=0, le=1)
    relevance_score: Optional[float] = Field(None, ge=0, le=1)
    connector_name: str
    raw_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "schema_version": "1.0",
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "fingerprint": "a" * 64,
                    "csl_json": {
                        "type": "article-journal",
                        "title": "Example Article",
                        "author": [{"family": "Doe", "given": "John"}],
                        "issued": {"date-parts": [[2023]]},
                        "container-title": "Journal of Examples",
                        "DOI": "10.1234/example",
                    },
                    "quality_score": 0.85,
                    "relevance_score": 0.92,
                    "connector_name": "openalex",
                    "created_at": "2023-01-01T00:00:00Z",
                }
            ]
        }
    )


class Evidence(BaseSchemaModel):
    """Extracted evidence model."""

    id: UUID
    run_id: UUID
    source_id: UUID
    evidence_type: EvidenceType
    content: str
    context: Optional[str] = None
    page_number: Optional[int] = Field(None, ge=1)
    section: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0, le=1)
    relevance_score: Optional[float] = Field(None, ge=0, le=1)
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class ClaimPosition(BaseModel):
    """Position of claim in document."""

    paragraph: int = Field(..., ge=0)
    sentence: int = Field(..., ge=0)


class ClaimMetadata(BaseModel):
    """Claim metadata."""

    nli_score: Optional[float] = Field(None, ge=0, le=1)
    contradicting_evidence_ids: Optional[List[UUID]] = None


class Claim(BaseSchemaModel):
    """Claim model."""

    id: UUID
    run_id: UUID
    claim_text: str
    claim_type: ClaimType
    supporting_evidence_ids: List[UUID]
    confidence_score: Optional[float] = Field(None, ge=0, le=1)
    verification_status: Optional[VerificationStatus] = None
    section_id: Optional[UUID] = None
    position: Optional[ClaimPosition] = None
    metadata: Optional[ClaimMetadata] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class DraftSectionMetadata(BaseModel):
    """Draft section metadata."""

    generated_by: Optional[str] = None
    generation_timestamp: Optional[datetime] = None
    revision: Optional[int] = Field(None, ge=1)


class DraftSection(BaseSchemaModel):
    """Draft section model."""

    id: UUID
    run_id: UUID
    section_type: SectionType
    title: str
    content: str
    order: int = Field(..., ge=0)
    evidence_ids: Optional[List[UUID]] = []
    claim_ids: Optional[List[UUID]] = []
    word_count: Optional[int] = Field(None, ge=0)
    metadata: Optional[DraftSectionMetadata] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ArtifactReference(BaseModel):
    """Reference to a stored artifact."""

    artifact_id: UUID
    filename: str
    file_path: str
    file_size: Optional[int] = Field(None, ge=0)
    checksum: str = Field(..., pattern="^[a-f0-9]{64}$")
    content_type: Optional[str] = None


class RunArtifacts(BaseModel):
    """Collection of run artifacts."""

    sources: Optional[List[ArtifactReference]] = []
    evidence: Optional[List[ArtifactReference]] = []
    draft_sections: Optional[List[ArtifactReference]] = []
    claims: Optional[List[ArtifactReference]] = []
    quality_report: Optional[ArtifactReference] = None
    final_output: Optional[ArtifactReference] = None


class RunMetrics(BaseModel):
    """Run execution metrics."""

    total_sources: Optional[int] = Field(0, ge=0)
    total_evidence: Optional[int] = Field(0, ge=0)
    total_claims: Optional[int] = Field(0, ge=0)
    word_count: Optional[int] = Field(0, ge=0)
    quality_score: Optional[float] = Field(None, ge=0, le=1)
    execution_time_seconds: Optional[float] = Field(None, ge=0)


class RunManifest(BaseSchemaModel):
    """Complete run manifest."""

    run_id: UUID
    thesis: str
    status: RunStatus
    pipeline_version: str
    configuration: Optional[Dict[str, Any]] = {}
    artifacts: Optional[RunArtifacts] = None
    metrics: Optional[RunMetrics] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class SourceLimits(BaseModel):
    """Source search limits."""

    max_sources: int = Field(50, ge=1, le=500)
    min_quality_score: float = Field(0.5, ge=0, le=1)
    publication_year_range: Optional[Dict[str, int]] = None


class ConnectorConfig(BaseModel):
    """Connector configuration."""

    name: str
    enabled: bool = True
    priority: Optional[int] = Field(None, ge=1, le=10)
    config: Optional[Dict[str, Any]] = {}


class QualityGates(BaseModel):
    """Quality gate thresholds."""

    min_evidence_per_claim: int = Field(2, ge=1)
    min_quality_score: float = Field(0.7, ge=0, le=1)
    max_passive_voice_percentage: float = Field(20, ge=0, le=100)
    min_readability_score: float = Field(60, ge=0, le=100)


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = Field("ollama", pattern="^(ollama|openai|anthropic)$")
    model: Optional[str] = None
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=1)


class AdvancedConfig(BaseModel):
    """Advanced configuration options."""

    enable_fact_checking: bool = True
    enable_adversarial_search: bool = True
    enable_claim_repair: bool = True
    chunk_size: int = Field(1000, ge=100, le=5000)
    overlap_size: int = Field(100, ge=0, le=500)


class RunConfiguration(BaseSchemaModel):
    """Run configuration model."""

    style_pack: StylePack = StylePack.ACADEMIC_REPORT
    target_word_count: int = Field(5000, ge=100, le=50000)
    language: str = "en"
    source_limits: Optional[SourceLimits] = None
    connectors: Optional[List[ConnectorConfig]] = None
    quality_gates: Optional[QualityGates] = None
    llm_config: Optional[LLMConfig] = None
    output_formats: List[str] = ["markdown", "pdf"]
    advanced: Optional[AdvancedConfig] = None


# Quality report models
class ReadabilityMetrics(BaseModel):
    """Readability metrics."""

    flesch_reading_ease: Optional[float] = None
    flesch_kincaid_grade: Optional[float] = None
    gunning_fog: Optional[float] = None
    smog_index: Optional[float] = None
    automated_readability_index: Optional[float] = None


class WritingQualityMetrics(BaseModel):
    """Writing quality metrics."""

    passive_voice_percentage: Optional[float] = Field(None, ge=0, le=100)
    sentence_complexity: Optional[float] = None
    average_sentence_length: Optional[float] = None
    vocabulary_diversity: Optional[float] = Field(None, ge=0, le=1)


class EvidenceQualityMetrics(BaseModel):
    """Evidence quality metrics."""

    average_evidence_per_claim: Optional[float] = None
    unsupported_claims: Optional[int] = Field(0, ge=0)
    evidence_diversity: Optional[float] = Field(None, ge=0, le=1)
    source_recency: Optional[float] = Field(None, ge=0, le=1)


class FactualAccuracyMetrics(BaseModel):
    """Factual accuracy metrics."""

    verified_claims: Optional[int] = Field(0, ge=0)
    disputed_claims: Optional[int] = Field(0, ge=0)
    unverifiable_claims: Optional[int] = Field(0, ge=0)
    accuracy_score: Optional[float] = Field(None, ge=0, le=1)


class CitationQualityMetrics(BaseModel):
    """Citation quality metrics."""

    citation_density: Optional[float] = None
    citation_diversity: Optional[float] = Field(None, ge=0, le=1)
    self_citation_percentage: Optional[float] = Field(None, ge=0, le=100)


class QualityMetrics(BaseModel):
    """All quality metrics."""

    readability: Optional[ReadabilityMetrics] = None
    writing_quality: Optional[WritingQualityMetrics] = None
    evidence_quality: Optional[EvidenceQualityMetrics] = None
    factual_accuracy: Optional[FactualAccuracyMetrics] = None
    citation_quality: Optional[CitationQualityMetrics] = None


class QualityIssueLocation(BaseModel):
    """Location of quality issue."""

    section_id: Optional[UUID] = None
    paragraph: Optional[int] = Field(None, ge=0)
    sentence: Optional[int] = Field(None, ge=0)


class QualityIssue(BaseModel):
    """Quality issue found."""

    severity: str = Field(..., pattern="^(error|warning|info)$")
    category: str = Field(..., pattern="^(readability|evidence|claims|citations|style|structure)$")
    message: str
    location: Optional[QualityIssueLocation] = None
    suggestion: Optional[str] = None


class QualityReport(BaseSchemaModel):
    """Quality assessment report."""

    run_id: UUID
    overall_score: float = Field(..., ge=0, le=1)
    passed: bool
    metrics: QualityMetrics
    issues: Optional[List[QualityIssue]] = []
    recommendations: Optional[List[str]] = []
    generated_at: datetime


# Event models
class EventProgress(BaseModel):
    """Event progress information."""

    current: Optional[int] = Field(None, ge=0)
    total: Optional[int] = Field(None, ge=0)
    percentage: Optional[float] = Field(None, ge=0, le=100)


class EventError(BaseModel):
    """Event error information."""

    code: Optional[str] = None
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    stack_trace: Optional[str] = None


class EventArtifact(BaseModel):
    """Event artifact reference."""

    artifact_id: UUID
    type: Optional[str] = None
    filename: Optional[str] = None


class EventPayload(BaseModel):
    """Event payload data."""

    message: Optional[str] = None
    progress: Optional[EventProgress] = None
    metrics: Optional[Dict[str, Any]] = None
    error: Optional[EventError] = None
    artifacts: Optional[List[EventArtifact]] = []


class EventMetadata(BaseModel):
    """Event metadata."""

    service: Optional[str] = None
    version: Optional[str] = None
    hostname: Optional[str] = None
    correlation_id: Optional[UUID] = None


class EventEnvelope(BaseSchemaModel):
    """Event envelope for pipeline events."""

    event_id: UUID
    run_id: UUID
    event_type: str
    timestamp: datetime
    stage: Optional[str] = None
    payload: Optional[EventPayload] = None
    metadata: Optional[EventMetadata] = None


# Additional models
class AccessRestrictions(BaseModel):
    """Access restrictions for evidence."""

    reason: str = Field(..., pattern="^(copyright|paywall|embargo|confidential|gdpr)$")
    access_url: Optional[str] = None
    license: Optional[str] = None
    embargo_until: Optional[datetime] = None


class LimitedAccessEvidence(BaseSchemaModel):
    """Limited access evidence model."""

    id: UUID
    source_id: UUID
    evidence_type: EvidenceType
    summary: str
    access_restrictions: AccessRestrictions
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class UserLibraryConfig(BaseModel):
    """User library configuration."""

    enabled: bool = True
    collection_ids: Optional[List[UUID]] = []


class Preferences(BaseModel):
    """User preferences."""

    citation_style: CitationStyle = CitationStyle.APA
    language_variant: str = Field("en-US", pattern="^en-(US|GB|AU|CA)$")
    formality_level: str = Field("formal", pattern="^(formal|semi-formal|informal)$")


class StructuredInput(BaseSchemaModel):
    """Structured input for pipeline."""

    thesis: str = Field(..., min_length=10, max_length=5000)
    context: Optional[str] = None
    objectives: Optional[List[str]] = []
    keywords: Optional[List[str]] = []
    outline: Optional[List[Dict[str, Any]]] = []
    constraints: Optional[Dict[str, Any]] = {}
    user_library: Optional[UserLibraryConfig] = None
    preferences: Optional[Preferences] = None


class Author(BaseModel):
    """Author information."""

    name: str
    orcid: Optional[str] = Field(None, pattern="^\\d{4}-\\d{4}-\\d{4}-\\d{3}[\\dX]$")
    affiliation: Optional[str] = None


class SearchResultIdentifiers(BaseModel):
    """Search result identifiers."""

    doi: Optional[str] = None
    pmid: Optional[str] = None
    arxiv_id: Optional[str] = None
    isbn: Optional[str] = None
    issn: Optional[str] = None


class SearchResultAccess(BaseModel):
    """Search result access information."""

    is_open_access: Optional[bool] = None
    pdf_url: Optional[str] = None
    html_url: Optional[str] = None
    repository_url: Optional[str] = None
    license: Optional[str] = None


class SearchResultVenue(BaseModel):
    """Search result venue information."""

    name: Optional[str] = None
    type: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None


class SearchResultMetrics(BaseModel):
    """Search result metrics."""

    citation_count: Optional[int] = Field(None, ge=0)
    altmetric_score: Optional[float] = Field(None, ge=0)
    download_count: Optional[int] = Field(None, ge=0)


class SearchResult(BaseSchemaModel):
    """Search result from connector."""

    connector_name: str
    result_id: str
    relevance_score: Optional[float] = Field(None, ge=0, le=1)
    title: str
    authors: Optional[List[Author]] = []
    publication_date: Optional[date] = None
    abstract: Optional[str] = None
    identifiers: Optional[SearchResultIdentifiers] = None
    access: Optional[SearchResultAccess] = None
    venue: Optional[SearchResultVenue] = None
    metrics: Optional[SearchResultMetrics] = None
    snippet: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BibliographyEntry(BaseModel):
    """Bibliography entry."""

    id: str
    source_id: UUID
    formatted_citation: str
    in_text_citation: str
    usage_count: Optional[int] = Field(0, ge=0)
    sections_used: Optional[List[str]] = []
    csl_json: Optional[CSLJSON] = None


class BibliographyStatistics(BaseModel):
    """Bibliography statistics."""

    total_sources: Optional[int] = Field(0, ge=0)
    unique_authors: Optional[int] = Field(0, ge=0)
    publication_year_range: Optional[Dict[str, int]] = None
    source_types: Optional[Dict[str, int]] = None


class Bibliography(BaseSchemaModel):
    """Bibliography for document."""

    run_id: UUID
    citation_style: CitationStyle
    entries: List[BibliographyEntry]
    statistics: Optional[BibliographyStatistics] = None
    generated_at: datetime
