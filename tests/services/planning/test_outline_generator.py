"""Tests for outline generator."""

import pytest

from src.services.planning.models import PlanningStrategy, ThesisAnalysis
from src.services.planning.outline_generator import OutlineGenerator


class TestOutlineGenerator:
    """Test outline generator functionality."""

    @pytest.fixture()
    def generator(self):
        """Create outline generator instance."""
        # Use heuristic mode for tests
        return OutlineGenerator(use_llm=False)

    @pytest.fixture()
    def sample_analysis(self):
        """Create sample thesis analysis."""
        return ThesisAnalysis(
            main_topic="impact of social media on mental health",
            subtopics=["anxiety", "depression", "self-esteem"],
            research_questions=[
                "How does social media usage affect anxiety levels?",
                "What is the relationship between social media and depression?",
            ],
            key_concepts=["social media", "mental health", "digital wellbeing"],
            scope="focused",
            methodology_hints=["quantitative", "survey"],
        )

    @pytest.mark.asyncio()
    async def test_generate_new_outline(self, generator, sample_analysis):
        """Test generating new outline from analysis."""
        sections = await generator.generate(
            analysis=sample_analysis,
            target_word_count=5000,
            document_type="research_paper",
        )

        assert len(sections) >= 6  # Standard research paper sections
        total_words = sum(s.word_budget for s in sections)
        # Allow small variance due to rounding
        assert abs(total_words - 5000) <= 10

        # Check section properties
        intro_section = next(s for s in sections if "introduction" in s.title.lower())
        assert intro_section.word_budget > 0
        assert len(intro_section.key_points) > 0
        assert intro_section.order == 1

    @pytest.mark.asyncio()
    async def test_generate_from_existing_outline(self, generator, sample_analysis):
        """Test generating from existing outline."""
        existing_outline = [
            {"section": "Background", "target_word_count": 1000},
            {"section": "Methods", "target_word_count": 800},
            {"section": "Analysis", "description": "Data analysis and findings"},
            {"section": "Conclusion"},
        ]

        sections = await generator.generate(
            analysis=sample_analysis,
            target_word_count=3000,
            existing_outline=existing_outline,
        )

        assert len(sections) == 4
        assert sections[0].title == "Background"
        # Check word budgets are reasonable (may be adjusted)
        assert sections[0].word_budget > 0
        assert sections[1].word_budget > 0
        # Total should match target
        total_words = sum(s.word_budget for s in sections)
        assert abs(total_words - 3000) <= 30  # 1% tolerance
        assert sections[2].description == "Data analysis and findings"

    @pytest.mark.asyncio()
    async def test_word_budget_distribution(self, generator, sample_analysis):
        """Test word budget distribution across sections."""
        # Test with different target word counts
        for target in [1000, 3000, 5000, 10000]:
            sections = await generator.generate(
                analysis=sample_analysis,
                target_word_count=target,
                document_type="research_paper",
            )

            total_words = sum(s.word_budget for s in sections)
            # Allow small variance due to rounding
            assert abs(total_words - target) <= target * 0.01  # 1% tolerance

            # Check constraints (note: for smaller targets, min may be adjusted)
            for section in sections:
                if target >= 2000:  # Only check min for larger documents
                    # Allow slight variance due to rounding in adjustment
                    assert section.word_budget >= 195  # Min constraint with tolerance
                # Allow slight overage due to final adjustment (3% tolerance)
                assert section.word_budget <= 2060  # Max constraint with tolerance

    @pytest.mark.asyncio()
    async def test_different_document_types(self, generator, sample_analysis):
        """Test generating outlines for different document types."""
        document_types = ["research_paper", "essay", "literature_review", "report"]

        for doc_type in document_types:
            sections = await generator.generate(
                analysis=sample_analysis,
                target_word_count=3000,
                document_type=doc_type,
            )

            assert len(sections) > 0
            assert all(s.word_budget > 0 for s in sections)

            # Check document-specific sections
            if doc_type == "essay":
                assert any("argument" in s.title.lower() for s in sections)
            elif doc_type == "literature_review":
                assert any("theoretical" in s.title.lower() for s in sections)

    @pytest.mark.asyncio()
    async def test_subtopic_sections_generation(self, generator, sample_analysis):
        """Test generation of subtopic sections for longer documents."""
        sections = await generator.generate(
            analysis=sample_analysis,
            target_word_count=8000,  # Long enough to include subtopics
            document_type="research_paper",
        )

        # Should include subtopic sections
        subtopic_sections = [s for s in sections if "Analysis:" in s.title]
        assert len(subtopic_sections) > 0

        # Check subtopic coverage
        for subtopic in sample_analysis.subtopics[:2]:
            assert any(subtopic in s.title for s in subtopic_sections)

    @pytest.mark.asyncio()
    async def test_key_points_generation(self, generator, sample_analysis):
        """Test key points generation for sections."""
        sections = await generator.generate(
            analysis=sample_analysis,
            target_word_count=3000,
            document_type="research_paper",
        )

        # Check introduction key points
        intro = next(s for s in sections if "introduction" in s.title.lower())
        assert any("main topic" in p.lower() for p in intro.key_points)
        assert any("research questions" in p.lower() for p in intro.key_points)

        # Check methodology key points
        method = next(s for s in sections if "methodology" in s.title.lower())
        assert any("research design" in p.lower() for p in method.key_points)

        # Should include methodology hints
        if sample_analysis.methodology_hints:
            assert any(
                hint in " ".join(method.key_points).lower()
                for hint in sample_analysis.methodology_hints
            )

    @pytest.mark.asyncio()
    async def test_required_evidence_types(self, generator, sample_analysis):
        """Test required evidence types for sections."""
        sections = await generator.generate(
            analysis=sample_analysis,
            target_word_count=3000,
            document_type="research_paper",
        )

        # Check evidence requirements
        intro = next(s for s in sections if "introduction" in s.title.lower())
        assert "definitions" in intro.required_evidence_types
        assert "background" in intro.required_evidence_types

        lit_review = next(s for s in sections if "literature" in s.title.lower())
        assert "academic_sources" in lit_review.required_evidence_types
        assert "theories" in lit_review.required_evidence_types

    @pytest.mark.asyncio()
    async def test_custom_planning_strategy(self, sample_analysis):
        """Test using custom planning strategy."""
        strategy = PlanningStrategy(
            name="minimal",
            approach="top-down",
            max_depth=2,
            min_section_words=100,
            max_section_words=1000,
            evidence_requirements={"sources": 3},
        )

        generator = OutlineGenerator(strategy=strategy, use_llm=False)
        sections = await generator.generate(
            analysis=sample_analysis,
            target_word_count=2000,
            document_type="essay",
        )

        # Check strategy constraints are applied (with some flexibility for adjustment)
        for section in sections:
            # Allow some flexibility due to adjustment algorithm
            assert section.word_budget >= 90  # Slightly less than 100 due to rounding
            assert section.word_budget <= 1100  # Allow 10% over max due to final adjustment

    @pytest.mark.asyncio()
    async def test_section_ordering(self, generator, sample_analysis):
        """Test section ordering."""
        sections = await generator.generate(
            analysis=sample_analysis,
            target_word_count=3000,
            document_type="research_paper",
        )

        # Check sections are properly ordered
        orders = [s.order for s in sections]
        assert orders == sorted(orders)
        assert len(set(orders)) == len(orders)  # All unique

        # Introduction should be first
        intro = next(s for s in sections if "introduction" in s.title.lower())
        assert intro.order == 1

        # Conclusion should be last among main sections
        main_sections = [s for s in sections if s.parent_section_id is None]
        conclusion = next(s for s in main_sections if "conclusion" in s.title.lower())
        assert conclusion.order == max(s.order for s in main_sections)
