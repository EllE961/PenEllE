"""Tests for search plan generator."""

import pytest

from src.services.planning.models import (
    DocumentSection,
    SearchPlan,
    ThesisAnalysis,
)
from src.services.planning.search_plan_generator import SearchPlanGenerator


class TestSearchPlanGenerator:
    """Test search plan generator functionality."""

    @pytest.fixture()
    def generator(self):
        """Create search plan generator instance."""
        return SearchPlanGenerator(use_llm=False)

    @pytest.fixture()
    def sample_analysis(self):
        """Create sample thesis analysis."""
        return ThesisAnalysis(
            main_topic="artificial intelligence in healthcare",
            subtopics=["diagnostic imaging", "predictive analytics", "clinical decision support"],
            research_questions=[
                "How can AI improve diagnostic accuracy?",
                "What are the ethical considerations of AI in healthcare?",
            ],
            key_concepts=[
                "machine learning",
                "deep learning",
                "medical AI",
                "healthcare technology",
            ],
            scope="broad",
            methodology_hints=["systematic review", "case study"],
        )

    @pytest.fixture()
    def sample_sections(self):
        """Create sample document sections."""
        return [
            DocumentSection(
                title="Introduction",
                description="Introduce AI in healthcare",
                word_budget=500,
                key_points=["Present main topic: artificial intelligence in healthcare"],
                order=1,
            ),
            DocumentSection(
                title="Literature Review",
                description="Review existing research",
                word_budget=1000,
                key_points=["Examine concept: machine learning", "Examine concept: deep learning"],
                order=2,
            ),
            DocumentSection(
                title="Methodology",
                description="Research methods",
                word_budget=500,
                key_points=["Apply systematic review approach"],
                order=3,
            ),
            DocumentSection(
                title="Results",
                description="Present findings",
                word_budget=800,
                key_points=["Present main findings"],
                order=4,
            ),
        ]

    @pytest.mark.asyncio()
    async def test_generate_search_plan(self, generator, sample_analysis, sample_sections):
        """Test generating basic search plan."""
        search_plan = await generator.generate(sample_analysis, sample_sections)

        assert isinstance(search_plan, SearchPlan)
        assert len(search_plan.queries) > 0
        assert len(search_plan.filters) > 0
        assert search_plan.total_expected_sources > 0
        assert search_plan.search_strategy in [
            "comprehensive",
            "targeted",
            "exploratory",
            "balanced",
        ]

    @pytest.mark.asyncio()
    async def test_query_generation(self, generator, sample_analysis, sample_sections):
        """Test search query generation."""
        search_plan = await generator.generate(sample_analysis, sample_sections)

        # Check primary query
        primary_query = search_plan.queries[0]
        assert primary_query.priority == 1
        assert "artificial intelligence in healthcare" in primary_query.query
        assert primary_query.expected_results > 10

        # Check queries cover research questions
        all_queries = " ".join(q.query for q in search_plan.queries)
        assert "diagnostic accuracy" in all_queries
        assert "ethical" in all_queries

        # Check concept queries
        for concept in ["machine learning", "deep learning"]:
            assert any(concept in q.query for q in search_plan.queries)

    @pytest.mark.asyncio()
    async def test_query_deduplication(self, generator, sample_analysis, sample_sections):
        """Test that duplicate queries are removed."""
        # Add duplicate keywords
        keywords = ["AI healthcare", "AI healthcare", "medical AI"]

        search_plan = await generator.generate(sample_analysis, sample_sections, keywords=keywords)

        # Check no duplicate queries
        query_texts = [q.query.lower() for q in search_plan.queries]
        assert len(query_texts) == len(set(query_texts))

    @pytest.mark.asyncio()
    async def test_section_specific_queries(self, generator, sample_analysis, sample_sections):
        """Test generation of section-specific queries."""
        search_plan = await generator.generate(sample_analysis, sample_sections)

        # Check literature review queries
        lit_queries = [q for q in search_plan.queries if "Literature Review" in q.purpose]
        assert any("systematic review" in q.query for q in lit_queries)
        assert any("theoretical framework" in q.query for q in lit_queries)

        # Check methodology queries
        method_queries = [q for q in search_plan.queries if "Methodology" in q.purpose]
        assert len(method_queries) > 0

    @pytest.mark.asyncio()
    async def test_filter_generation(self, generator, sample_analysis, sample_sections):
        """Test search filter generation."""
        search_plan = await generator.generate(sample_analysis, sample_sections)

        # Check basic filters
        filter_fields = [f.field for f in search_plan.filters]
        assert "publication_date" in filter_fields
        assert "language" in filter_fields
        assert "document_type" in filter_fields

        # Check date filter is recent
        date_filter = next(f for f in search_plan.filters if f.field == "publication_date")
        assert date_filter.operator == "gte"
        assert "2018" in str(date_filter.value) or "2019" in str(date_filter.value)

        # Check language filter
        lang_filter = next(f for f in search_plan.filters if f.field == "language")
        assert lang_filter.value == "en"

    @pytest.mark.asyncio()
    async def test_constraints_handling(self, generator, sample_analysis, sample_sections):
        """Test handling of search constraints."""
        constraints = {
            "excluded_sources": ["doi:10.1234/excluded1", "doi:10.1234/excluded2"],
            "publication_years": {"min": 2020, "max": 2023},
        }

        search_plan = await generator.generate(
            sample_analysis, sample_sections, constraints=constraints
        )

        # Check exclusion filters
        exclusion_filters = [f for f in search_plan.filters if f.operator == "ne"]
        assert len(exclusion_filters) == 2

        # Check year filters
        year_filters = [f for f in search_plan.filters if f.field == "publication_year"]
        assert any(f.operator == "gte" and f.value == 2020 for f in year_filters)
        assert any(f.operator == "lte" and f.value == 2023 for f in year_filters)

    @pytest.mark.asyncio()
    async def test_expected_sources_calculation(self, generator, sample_analysis):
        """Test calculation of expected sources."""
        # Small document
        small_sections = [
            DocumentSection(title=f"Section {i}", description="", word_budget=300, order=i)
            for i in range(3)
        ]
        small_plan = await generator.generate(sample_analysis, small_sections)

        # Large document
        large_sections = [
            DocumentSection(title=f"Section {i}", description="", word_budget=1000, order=i)
            for i in range(8)
        ]
        large_plan = await generator.generate(sample_analysis, large_sections)

        # Large documents should expect more sources
        assert large_plan.total_expected_sources > small_plan.total_expected_sources

        # Check bounds
        assert 20 <= small_plan.total_expected_sources <= 100
        assert 20 <= large_plan.total_expected_sources <= 100

    @pytest.mark.asyncio()
    async def test_search_strategy_determination(self, generator, sample_sections):
        """Test search strategy determination."""
        # Broad scope
        broad_analysis = ThesisAnalysis(
            main_topic="climate change",
            subtopics=[],
            research_questions=[],
            key_concepts=[],
            scope="broad",
            methodology_hints=[],
        )
        broad_plan = await generator.generate(broad_analysis, sample_sections[:8])
        assert broad_plan.search_strategy == "comprehensive"

        # Focused scope
        focused_analysis = ThesisAnalysis(
            main_topic="specific protein interaction",
            subtopics=[],
            research_questions=[],
            key_concepts=[],
            scope="focused",
            methodology_hints=[],
        )
        focused_plan = await generator.generate(focused_analysis, sample_sections[:3])
        assert focused_plan.search_strategy == "targeted"

        # Exploratory scope
        exploratory_analysis = ThesisAnalysis(
            main_topic="emerging technology",
            subtopics=[],
            research_questions=[],
            key_concepts=[],
            scope="exploratory",
            methodology_hints=[],
        )
        exploratory_plan = await generator.generate(exploratory_analysis, sample_sections)
        assert exploratory_plan.search_strategy == "exploratory"

    @pytest.mark.asyncio()
    async def test_query_priority_ordering(self, generator, sample_analysis, sample_sections):
        """Test that queries are properly prioritized."""
        search_plan = await generator.generate(sample_analysis, sample_sections)

        # Check queries are sorted by priority
        priorities = [q.priority for q in search_plan.queries]
        assert priorities == sorted(priorities)

        # Primary query should be first
        assert search_plan.queries[0].priority == 1
        assert search_plan.queries[0].purpose == "Primary topic search"

    @pytest.mark.asyncio()
    async def test_keyword_integration(self, generator, sample_analysis, sample_sections):
        """Test integration of user-provided keywords."""
        keywords = ["FDA approval", "clinical trials", "patient safety", "HIPAA compliance"]

        search_plan = await generator.generate(sample_analysis, sample_sections, keywords=keywords)

        # Check keywords are included in queries
        query_texts = " ".join(q.query for q in search_plan.queries)
        for keyword in keywords:
            assert keyword in query_texts

        # Check keyword queries have appropriate priority
        keyword_queries = [q for q in search_plan.queries if "Keyword:" in q.purpose]
        assert all(q.priority >= 4 for q in keyword_queries)
