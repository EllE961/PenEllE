"""Outline generator for creating document structure."""


import json
from uuid import uuid4

from src.core.llm import LLMClient
from src.core.logging.structured import get_logger

from .models import DocumentSection, PlanningStrategy, ThesisAnalysis

logger = get_logger(__name__)


class OutlineGenerator:
    """Generates document outline with sections and word budgets."""

    def __init__(self, strategy: PlanningStrategy | None = None, use_llm: bool = True):
        """Initialize outline generator.

        Args:
            strategy: Planning strategy to use
            use_llm: Whether to use LLM for generation
        """
        self.strategy = strategy or self._default_strategy()
        self.use_llm = use_llm
        if use_llm:
            from src.core.config.loader import load_config

            pipeline_dict = load_config("pipeline")
            model_name = pipeline_dict.get("default_models", {}).get("outline", "ollama-mixtral")
            self.llm = LLMClient(model_name=model_name)

    async def generate(
        self,
        analysis: ThesisAnalysis,
        target_word_count: int,
        existing_outline: list[dict] | None = None,
        document_type: str = "research_paper",
    ) -> list[DocumentSection]:
        """Generate document outline.

        Args:
            analysis: Thesis analysis results
            target_word_count: Target total word count
            existing_outline: Optional existing outline to build from
            document_type: Type of document

        Returns:
            List of document sections
        """
        logger.info(
            "Generating outline",
            target_words=target_word_count,
            document_type=document_type,
            has_existing_outline=bool(existing_outline),
        )

        if existing_outline:
            sections = self._generate_from_existing(existing_outline, target_word_count)
        elif self.use_llm:
            sections = await self._generate_with_llm(analysis, target_word_count, document_type)
        else:
            sections = self._generate_new_outline(analysis, target_word_count, document_type)

        # Validate and adjust word budgets
        sections = self._adjust_word_budgets(sections, target_word_count)

        logger.info(
            "Outline generated",
            num_sections=len(sections),
            total_words=sum(s.word_budget for s in sections),
        )

        return sections

    async def _generate_with_llm(
        self, analysis: ThesisAnalysis, target_word_count: int, document_type: str
    ) -> list[DocumentSection]:
        """Generate outline using LLM."""
        system_prompt = f"""You are an expert academic writer. Create a detailed outline for a {document_type}.
        The outline should include sections with specific word budgets that total {target_word_count} words.

        Return a JSON array of sections with this structure:
        [
            {{
                "title": "Section Title",
                "description": "What this section covers",
                "word_budget": 500,
                "key_points": ["Key point 1", "Key point 2"],
                "required_evidence_types": ["statistics", "case_studies"]
            }}
        ]

        Ensure:
        1. Word budgets sum to approximately {target_word_count}
        2. Sections are logically ordered
        3. Each section has a clear purpose
        4. Key points are specific to the thesis topic"""

        user_prompt = f"""Create an outline for this research:

        Topic: {analysis.main_topic}
        Subtopics: {', '.join(analysis.subtopics)}
        Research Questions: {'; '.join(analysis.research_questions[:3])}
        Key Concepts: {', '.join(analysis.key_concepts[:5])}
        Scope: {analysis.scope}
        Document Type: {document_type}
        Target Word Count: {target_word_count}"""

        try:
            response = await self.llm.generate(
                prompt=user_prompt, system=system_prompt, temperature=0.4, max_tokens=2000
            )

            # Parse JSON response
            try:
                json_start = response.find("[")
                json_end = response.rfind("]") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    sections_data = json.loads(json_str)
                else:
                    raise ValueError("No JSON array found in response")

                sections = []
                for i, section_data in enumerate(sections_data):
                    section = DocumentSection(
                        section_id=str(uuid4()),
                        title=section_data.get("title", f"Section {i + 1}"),
                        description=section_data.get("description", ""),
                        word_budget=section_data.get(
                            "word_budget", target_word_count // len(sections_data)
                        ),
                        key_points=section_data.get("key_points", []),
                        required_evidence_types=section_data.get("required_evidence_types", []),
                        order=i + 1,
                    )
                    sections.append(section)

                logger.info(
                    "Generated outline with LLM",
                    num_sections=len(sections),
                    total_words=sum(s.word_budget for s in sections),
                )

                return sections

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "Failed to parse LLM outline response, falling back to template", error=str(e)
                )
                return self._generate_new_outline(analysis, target_word_count, document_type)

        except Exception:
            logger.exception("LLM outline generation failed, falling back to template")
            return self._generate_new_outline(analysis, target_word_count, document_type)

    def _generate_from_existing(
        self, existing_outline: list[dict], target_word_count: int
    ) -> list[DocumentSection]:
        """Generate sections from existing outline.

        Args:
            existing_outline: Existing outline structure
            target_word_count: Target total word count

        Returns:
            List of document sections
        """
        sections = []

        for i, item in enumerate(existing_outline):
            # Calculate word budget
            if "target_word_count" in item and item["target_word_count"] > 0:
                word_budget = item["target_word_count"]
            else:
                # Distribute remaining words equally
                word_budget = target_word_count // len(existing_outline)

            section = DocumentSection(
                title=item["section"],
                description=item.get("description", f"Content for {item['section']}"),
                word_budget=word_budget,
                key_points=item.get("key_points", []),
                order=i + 1,
            )
            sections.append(section)

        return sections

    def _generate_new_outline(
        self, analysis: ThesisAnalysis, target_word_count: int, document_type: str
    ) -> list[DocumentSection]:
        """Generate new outline based on analysis.

        Args:
            analysis: Thesis analysis results
            target_word_count: Target total word count
            document_type: Type of document

        Returns:
            List of document sections
        """
        # Get template based on document type
        template = self._get_document_template(document_type)

        # Calculate base word distribution
        base_sections = len(template)
        base_word_budget = target_word_count // base_sections

        sections = []
        for i, (title, weight, description) in enumerate(template):
            # Adjust word budget based on weight
            word_budget = int(base_word_budget * weight)

            # Generate key points based on analysis
            key_points = self._generate_key_points(title, analysis)

            section = DocumentSection(
                title=title,
                description=description,
                word_budget=word_budget,
                key_points=key_points,
                order=i + 1,
                required_evidence_types=self._get_required_evidence(title),
            )
            sections.append(section)

        # Add sections for subtopics if needed
        SUBTOPIC_WORD_THRESHOLD = 3000
        if len(analysis.subtopics) > 0 and target_word_count > SUBTOPIC_WORD_THRESHOLD:
            sections.extend(self._generate_subtopic_sections(analysis.subtopics, target_word_count))

        return sections

    def _get_document_template(self, document_type: str) -> list[tuple[str, float, str]]:
        """Get document template based on type.

        Args:
            document_type: Type of document

        Returns:
            List of (title, weight, description) tuples
        """
        templates = {
            "research_paper": [
                ("Introduction", 0.15, "Introduce the topic and research questions"),
                ("Literature Review", 0.25, "Review existing research and identify gaps"),
                ("Methodology", 0.15, "Describe research methods and approach"),
                ("Results", 0.2, "Present findings and analysis"),
                ("Discussion", 0.15, "Interpret results and implications"),
                ("Conclusion", 0.1, "Summarize findings and future directions"),
            ],
            "essay": [
                ("Introduction", 0.15, "Introduce the thesis and outline"),
                ("Main Arguments", 0.6, "Present and support main arguments"),
                ("Counter-arguments", 0.15, "Address opposing viewpoints"),
                ("Conclusion", 0.1, "Summarize and reinforce thesis"),
            ],
            "literature_review": [
                ("Introduction", 0.1, "Define scope and objectives"),
                ("Theoretical Background", 0.2, "Establish theoretical framework"),
                ("Thematic Analysis", 0.5, "Analyze themes in literature"),
                ("Gaps and Opportunities", 0.1, "Identify research gaps"),
                ("Conclusion", 0.1, "Synthesize findings"),
            ],
            "report": [
                ("Executive Summary", 0.1, "High-level overview"),
                ("Introduction", 0.1, "Background and objectives"),
                ("Analysis", 0.5, "Detailed analysis and findings"),
                ("Recommendations", 0.2, "Actionable recommendations"),
                ("Conclusion", 0.1, "Summary and next steps"),
            ],
        }

        return templates.get(document_type, templates["research_paper"])

    def _generate_key_points(self, section_title: str, analysis: ThesisAnalysis) -> list[str]:
        """Generate key points for a section.

        Args:
            section_title: Title of the section
            analysis: Thesis analysis results

        Returns:
            List of key points
        """
        key_points = []

        # Map section types to relevant analysis components
        if "introduction" in section_title.lower():
            key_points.extend(
                [
                    f"Present main topic: {analysis.main_topic}",
                    "State research questions",
                    "Outline document structure",
                ]
            )
            if analysis.research_questions:
                key_points.append(f"Address: {analysis.research_questions[0]}")

        elif "literature" in section_title.lower() or "review" in section_title.lower():
            key_points.extend(
                [
                    "Review existing research",
                    "Identify theoretical frameworks",
                    "Highlight research gaps",
                ]
            )
            for concept in analysis.key_concepts[:3]:
                key_points.append(f"Examine concept: {concept}")

        elif "methodology" in section_title.lower():
            key_points.extend(
                [
                    "Describe research design",
                    "Explain data collection methods",
                    "Discuss analysis approach",
                ]
            )
            if analysis.methodology_hints:
                key_points.append(f"Apply {analysis.methodology_hints[0]} approach")

        elif "result" in section_title.lower() or "finding" in section_title.lower():
            key_points.extend(
                [
                    "Present main findings",
                    "Use visual representations",
                    "Highlight significant patterns",
                ]
            )

        elif "discussion" in section_title.lower():
            key_points.extend(
                [
                    "Interpret findings",
                    "Compare with existing literature",
                    "Discuss implications",
                    "Address limitations",
                ]
            )

        elif "conclusion" in section_title.lower():
            key_points.extend(
                [
                    "Summarize key findings",
                    "Restate thesis",
                    "Suggest future research",
                ]
            )

        return key_points

    def _get_required_evidence(self, section_title: str) -> list[str]:
        """Get required evidence types for a section.

        Args:
            section_title: Title of the section

        Returns:
            List of required evidence types
        """
        evidence_map = {
            "introduction": ["definitions", "background", "statistics"],
            "literature": ["academic_sources", "theories", "previous_studies"],
            "methodology": ["method_descriptions", "justifications", "precedents"],
            "results": ["data", "analysis", "visualizations"],
            "discussion": ["comparisons", "interpretations", "implications"],
            "conclusion": ["summary", "recommendations", "future_directions"],
        }

        section_lower = section_title.lower()
        for key, evidence in evidence_map.items():
            if key in section_lower:
                return evidence

        return ["general_evidence"]

    def _generate_subtopic_sections(
        self, subtopics: list[str], target_word_count: int
    ) -> list[DocumentSection]:
        """Generate sections for subtopics.

        Args:
            subtopics: List of subtopics
            target_word_count: Target total word count

        Returns:
            List of subtopic sections
        """
        # Allocate 30% of words to subtopics
        subtopic_budget = int(target_word_count * 0.3)
        words_per_subtopic = subtopic_budget // len(subtopics)

        sections = []
        for i, subtopic in enumerate(subtopics):
            section = DocumentSection(
                title=f"Analysis: {subtopic}",
                description=f"Detailed analysis of {subtopic}",
                word_budget=words_per_subtopic,
                key_points=[
                    f"Define {subtopic}",
                    f"Analyze {subtopic} in context",
                    "Discuss implications",
                ],
                order=20 + i,  # Place after main sections
            )
            sections.append(section)

        return sections

    def _adjust_word_budgets(
        self, sections: list[DocumentSection], target_word_count: int
    ) -> list[DocumentSection]:
        """Adjust word budgets to meet target.

        Args:
            sections: List of sections
            target_word_count: Target total word count

        Returns:
            Adjusted sections
        """
        current_total = sum(s.word_budget for s in sections)

        if current_total == target_word_count:
            return sections

        # Calculate adjustment ratio
        ratio = target_word_count / current_total

        for section in sections:
            # Adjust budget
            new_budget = int(section.word_budget * ratio)

            # Enforce min/max constraints (but be flexible for small documents)
            if target_word_count >= len(sections) * self.strategy.min_section_words:
                new_budget = max(self.strategy.min_section_words, new_budget)
            new_budget = min(self.strategy.max_section_words, new_budget)

            section.word_budget = new_budget

        # Handle any remaining difference
        final_total = sum(s.word_budget for s in sections)
        if final_total != target_word_count:
            diff = target_word_count - final_total
            # Distribute difference across sections
            per_section = diff // len(sections)
            for section in sections:
                section.word_budget += per_section

        return sections

    def _default_strategy(self) -> PlanningStrategy:
        """Get default planning strategy.

        Returns:
            Default planning strategy
        """
        return PlanningStrategy(
            name="default",
            approach="top-down",
            max_depth=3,
            min_section_words=200,
            max_section_words=2000,
            evidence_requirements={
                "academic_sources": 5,
                "definitions": 3,
                "examples": 2,
            },
        )
