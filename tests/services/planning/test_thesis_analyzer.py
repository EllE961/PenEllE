"""Tests for thesis analyzer."""

import pytest

from src.services.planning.models import ThesisAnalysis
from src.services.planning.thesis_analyzer import ThesisAnalyzer


class TestThesisAnalyzer:
    """Test thesis analyzer functionality."""

    @pytest.fixture()
    def analyzer(self):
        """Create thesis analyzer instance."""
        # Use heuristic mode for tests to avoid LLM dependency
        return ThesisAnalyzer(use_llm=False)

    @pytest.mark.asyncio()
    async def test_analyze_simple_thesis(self, analyzer):
        """Test analyzing a simple thesis."""
        thesis = "This research investigates the impact of climate change on coastal ecosystems."

        analysis = await analyzer.analyze(thesis)

        assert isinstance(analysis, ThesisAnalysis)
        assert analysis.main_topic == "the impact of climate change on coastal ecosystems"
        assert analysis.scope in ["broad", "focused", "exploratory", "comparative", "case_study"]
        # Simple thesis may not have extracted concepts, that's ok
        assert isinstance(analysis.key_concepts, list)

    @pytest.mark.asyncio()
    async def test_analyze_thesis_with_context(self, analyzer):
        """Test analyzing thesis with additional context."""
        thesis = "This study examines machine learning applications in healthcare."
        context = "The research focuses on diagnostic imaging and predictive analytics for patient outcomes."

        analysis = await analyzer.analyze(thesis, context)

        assert analysis.main_topic == "machine learning applications in healthcare"
        assert len(analysis.subtopics) > 0
        assert any("diagnostic imaging" in topic.lower() for topic in analysis.subtopics)

    @pytest.mark.asyncio()
    async def test_extract_research_questions(self, analyzer):
        """Test extracting research questions."""
        thesis = (
            "This research aims to understand how social media affects mental health "
            "in teenagers. What are the key risk factors? How can we mitigate negative impacts?"
        )

        analysis = await analyzer.analyze(thesis)

        assert len(analysis.research_questions) >= 2
        assert any("risk factors" in q for q in analysis.research_questions)
        assert any("mitigate" in q for q in analysis.research_questions)

    @pytest.mark.asyncio()
    async def test_extract_key_concepts(self, analyzer):
        """Test extracting key concepts."""
        thesis = (
            'This study explores "deep learning" and "neural networks" '
            "using the Transformer Model approach for Natural Language Processing."
        )

        analysis = await analyzer.analyze(thesis)

        assert "deep learning" in analysis.key_concepts
        assert "neural networks" in analysis.key_concepts
        assert any("transformer" in c.lower() for c in analysis.key_concepts)

    @pytest.mark.asyncio()
    async def test_determine_scope(self, analyzer):
        """Test scope determination."""
        # Broad scope
        thesis_broad = (
            "This comprehensive research investigates multiple aspects of "
            "climate change including environmental, economic, and social impacts."
        )
        analysis_broad = await analyzer.analyze(thesis_broad)
        assert analysis_broad.scope == "broad"

        # Focused scope
        thesis_focused = (
            "This focused study examines the specific impact of microplastics "
            "on marine life in the Pacific Ocean."
        )
        analysis_focused = await analyzer.analyze(thesis_focused)
        assert analysis_focused.scope == "focused"

        # Case study scope
        thesis_case = (
            "This case study analyzes the digital transformation of a single retail company."
        )
        analysis_case = await analyzer.analyze(thesis_case)
        assert analysis_case.scope == "case_study"

    @pytest.mark.asyncio()
    async def test_extract_methodology_hints(self, analyzer):
        """Test extracting methodology hints."""
        thesis = (
            "This research uses statistical analysis and surveys to measure "
            "the effectiveness of online learning platforms."
        )

        analysis = await analyzer.analyze(thesis)

        assert len(analysis.methodology_hints) > 0
        assert "quantitative" in analysis.methodology_hints

    @pytest.mark.asyncio()
    async def test_complex_thesis_analysis(self, analyzer):
        """Test analyzing a complex thesis."""
        thesis = (
            "This interdisciplinary research investigates the intersection of "
            "artificial intelligence and ethics in autonomous vehicles, examining "
            "decision-making algorithms, moral frameworks, and regulatory challenges. "
            "The study employs both quantitative analysis of accident data and "
            "qualitative interviews with stakeholders."
        )
        context = (
            "Key areas include: 1) Trolley problem scenarios, 2) Liability frameworks, "
            "3) Cultural differences in ethical priorities. The research aims to "
            "develop guidelines for ethical AI implementation in transportation."
        )

        analysis = await analyzer.analyze(thesis, context)

        assert "artificial intelligence and ethics in autonomous vehicles" in analysis.main_topic
        assert len(analysis.subtopics) >= 3
        assert len(analysis.key_concepts) >= 3
        assert "quantitative" in analysis.methodology_hints
        assert "qualitative" in analysis.methodology_hints
        assert any("trolley problem" in s.lower() for s in analysis.subtopics)

    @pytest.mark.asyncio()
    async def test_empty_thesis_handling(self, analyzer):
        """Test handling empty or very short thesis."""
        # Empty thesis should still return valid analysis
        analysis = await analyzer.analyze("")
        assert isinstance(analysis, ThesisAnalysis)
        assert analysis.main_topic == ""

        # Very short thesis
        analysis_short = await analyzer.analyze("AI ethics")
        assert isinstance(analysis_short, ThesisAnalysis)
        assert analysis_short.main_topic == "AI ethics"
