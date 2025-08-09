"""Models for the planning service."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.schemas.models import BaseSchemaModel


class DocumentSection(BaseModel):
    """Represents a planned document section."""

    section_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(..., description="Section title")
    description: str = Field(..., description="Section description")
    word_budget: int = Field(..., ge=0, description="Target word count")
    key_points: list[str] = Field(default_factory=list, description="Key points to cover")
    required_evidence_types: list[str] = Field(
        default_factory=list, description="Types of evidence needed"
    )
    parent_section_id: str | None = Field(
        None, description="Parent section for hierarchical structure"
    )
    order: int = Field(..., description="Section order in document")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SearchQuery(BaseModel):
    """Represents a search query for sourcing."""

    query: str = Field(..., description="Search query text")
    purpose: str = Field(..., description="Purpose of this query")
    expected_results: int = Field(default=10, description="Expected number of results")
    priority: int = Field(default=1, description="Query priority (1=highest)")


class SearchFilter(BaseModel):
    """Search filter criteria."""

    field: str = Field(..., description="Field to filter on")
    operator: str = Field(..., description="Filter operator (eq, ne, gt, lt, contains)")
    value: Any = Field(..., description="Filter value")


class SearchPlan(BaseModel):
    """Search plan for sourcing stage."""

    queries: list[SearchQuery] = Field(..., description="List of search queries")
    filters: list[SearchFilter] = Field(default_factory=list, description="Search filters")
    total_expected_sources: int = Field(..., description="Total expected sources")
    search_strategy: str = Field(default="comprehensive", description="Search strategy")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class PlanRequest(BaseSchemaModel):
    """Request for planning service."""

    thesis: str = Field(..., min_length=10, max_length=5000, description="Main thesis")
    context: str | None = Field(None, description="Additional context")
    objectives: list[str] = Field(default_factory=list, description="Specific objectives")
    keywords: list[str] = Field(default_factory=list, description="Key terms and concepts")
    outline: list[dict[str, Any]] | None = Field(None, description="Suggested outline")
    constraints: dict[str, Any] = Field(default_factory=dict, description="Planning constraints")
    target_word_count: int = Field(default=5000, ge=500, description="Target document word count")
    academic_level: str = Field(default="undergraduate", description="Academic level")
    document_type: str = Field(default="research_paper", description="Type of document")


class PlanResponse(BaseSchemaModel):
    """Response from planning service."""

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    sections: list[DocumentSection] = Field(..., description="Document sections")
    search_plan: SearchPlan = Field(..., description="Search plan for sourcing")
    estimated_completion_time: int = Field(..., description="Estimated minutes to complete")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ThesisAnalysis(BaseModel):
    """Analysis of the input thesis."""

    main_topic: str = Field(..., description="Main topic identified")
    subtopics: list[str] = Field(..., description="Subtopics identified")
    research_questions: list[str] = Field(..., description="Research questions extracted")
    key_concepts: list[str] = Field(..., description="Key concepts identified")
    scope: str = Field(..., description="Scope of the research")
    methodology_hints: list[str] = Field(default_factory=list, description="Methodology hints")


class PlanningStrategy(BaseModel):
    """Planning strategy configuration."""

    name: str = Field(..., description="Strategy name")
    approach: str = Field(..., description="Planning approach (top-down, bottom-up, hybrid)")
    max_depth: int = Field(default=3, description="Maximum section depth")
    min_section_words: int = Field(default=200, description="Minimum words per section")
    max_section_words: int = Field(default=2000, description="Maximum words per section")
    evidence_requirements: dict[str, int] = Field(
        default_factory=dict, description="Evidence requirements by type"
    )
