"""Thesis analyzer for extracting key information from research thesis."""

import json
import re

from src.core.config.loader import load_config
from src.core.llm import LLMClient
from src.core.logging.structured import get_logger

from .models import ThesisAnalysis

logger = get_logger(__name__)


class ThesisAnalyzer:
    """Analyzes thesis to extract key concepts and requirements."""

    def __init__(self, use_llm: bool = True):
        """Initialize thesis analyzer.

        Args:
            use_llm: Whether to use LLM for analysis (default: True)
        """
        self.use_llm = use_llm
        if use_llm:
            # Use planning model or default to research model
            pipeline_dict = load_config("pipeline")
            model_name = pipeline_dict.get("default_models", {}).get("research", "ollama-mixtral")
            self.llm = LLMClient(model_name=model_name)

    async def analyze(self, thesis: str, context: str | None = None) -> ThesisAnalysis:
        """Analyze thesis to extract key information.

        Args:
            thesis: The main thesis statement
            context: Additional context

        Returns:
            ThesisAnalysis with extracted information
        """
        logger.info("Analyzing thesis", thesis_length=len(thesis), use_llm=self.use_llm)

        if self.use_llm:
            return await self._analyze_with_llm(thesis, context)
        # Fallback to heuristic analysis
        return self._analyze_with_heuristics(thesis, context)

    async def _analyze_with_llm(self, thesis: str, context: str | None = None) -> ThesisAnalysis:
        """Analyze thesis using LLM."""
        system_prompt = """You are an expert research analyst. Analyze the given thesis and extract key information.
        Return a JSON object with the following structure:
        {
            "main_topic": "The main topic or subject of the research",
            "subtopics": ["List of subtopics or aspects to be covered"],
            "research_questions": ["List of research questions to be addressed"],
            "key_concepts": ["List of important concepts, theories, or terms"],
            "scope": "One of: broad, focused, exploratory, comparative, case_study",
            "methodology_hints": ["List of methodological approaches mentioned or implied"]
        }
        Be specific and extract actual information from the thesis, not generic placeholders."""

        user_prompt = f"""Thesis: {thesis}"""
        if context:
            user_prompt += f"\n\nAdditional Context: {context}"

        try:
            response = await self.llm.generate(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.3,  # Lower temperature for more consistent extraction
                max_tokens=1000,
            )

            # Parse JSON response
            try:
                # Extract JSON from response (in case LLM adds extra text)
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    data = json.loads(json_str)
                else:
                    raise ValueError("No JSON found in response")

                return ThesisAnalysis(
                    main_topic=data.get("main_topic", thesis[:100]),
                    subtopics=data.get("subtopics", [])[:5],
                    research_questions=data.get("research_questions", [])[:5],
                    key_concepts=data.get("key_concepts", [])[:10],
                    scope=data.get("scope", "focused"),
                    methodology_hints=data.get("methodology_hints", []),
                )
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "Failed to parse LLM response as JSON, falling back to heuristics",
                    error=str(e),
                    response_preview=response[:200],
                )
                return self._analyze_with_heuristics(thesis, context)

        except Exception:
            logger.exception("LLM analysis failed, falling back to heuristics")
            return self._analyze_with_heuristics(thesis, context)

    def _analyze_with_heuristics(self, thesis: str, context: str | None = None) -> ThesisAnalysis:
        """Analyze thesis using heuristic methods (fallback)."""
        # Extract main topic
        main_topic = self._extract_main_topic(thesis)

        # Extract subtopics
        subtopics = self._extract_subtopics(thesis, context)

        # Extract research questions
        research_questions = self._extract_research_questions(thesis, context)

        # Extract key concepts
        key_concepts = self._extract_key_concepts(thesis, context)

        # Determine scope
        scope = self._determine_scope(thesis, context)

        # Extract methodology hints
        methodology_hints = self._extract_methodology_hints(thesis, context)

        analysis = ThesisAnalysis(
            main_topic=main_topic,
            subtopics=subtopics,
            research_questions=research_questions,
            key_concepts=key_concepts,
            scope=scope,
            methodology_hints=methodology_hints,
        )

        logger.info(
            "Thesis analysis complete (heuristic)",
            main_topic=main_topic,
            num_subtopics=len(subtopics),
            num_concepts=len(key_concepts),
        )

        return analysis

    def _extract_main_topic(self, thesis: str) -> str:
        """Extract the main topic from thesis.

        Args:
            thesis: The thesis statement

        Returns:
            Main topic
        """
        # Simple heuristic: extract the main subject
        # In production, this would use NLP/LLM
        sentences = thesis.split(".")
        first_sentence = sentences[0] if sentences else thesis

        # Remove common prefixes
        prefixes = [
            "This research investigates",
            "This study examines",
            "This paper explores",
            "The purpose of this research is to",
        ]

        main_topic = first_sentence
        for prefix in prefixes:
            if main_topic.lower().startswith(prefix.lower()):
                main_topic = main_topic[len(prefix) :].strip()
                break

        return main_topic.strip()

    def _extract_subtopics(self, thesis: str, context: str | None = None) -> list[str]:
        """Extract subtopics from thesis and context.

        Args:
            thesis: The thesis statement
            context: Additional context

        Returns:
            List of subtopics
        """
        subtopics = []
        combined_text = thesis
        if context:
            combined_text += " " + context

        # Look for enumerated items
        enum_patterns = [
            r"(?:first|second|third|finally)[,:]?\s*([^.;]+)",
            r"\d+\)\s*([^,;]+)",  # Match until comma or semicolon
            r"[a-zA-Z]\)\s*([^,;]+)",
        ]

        for pattern in enum_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            subtopics.extend([m.strip() for m in matches])

        # Look for conjunctions indicating multiple topics
        if " and " in combined_text:
            # Extract topics separated by "and" in context
            and_pattern = r"([^,\.]+?)\s+and\s+([^,\.]+)"
            matches = re.findall(and_pattern, combined_text)
            for match in matches:
                subtopics.extend([match[0].strip(), match[1].strip()])

        # Deduplicate
        seen = set()
        unique_subtopics = []
        for topic in subtopics:
            if topic.lower() not in seen:
                seen.add(topic.lower())
                unique_subtopics.append(topic)

        return unique_subtopics[:5]  # Limit to 5 subtopics

    def _extract_research_questions(self, thesis: str, context: str | None = None) -> list[str]:
        """Extract research questions.

        Args:
            thesis: The thesis statement
            context: Additional context

        Returns:
            List of research questions
        """
        questions = []
        combined_text = thesis
        if context:
            combined_text += " " + context

        # Look for explicit questions
        question_pattern = r"[^.!?]*\?[^.!?]*"
        matches = re.findall(question_pattern, combined_text)
        questions.extend([m.strip() for m in matches])

        # Look for implicit questions
        implicit_patterns = [
            r"to understand ([^.]+)",
            r"to investigate ([^.]+)",
            r"to examine ([^.]+)",
            r"to analyze ([^.]+)",
            r"to explore ([^.]+)",
        ]

        for pattern in implicit_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                questions.append(f"How {match.strip()}?")

        return questions[:5]  # Limit to 5 questions

    def _extract_key_concepts(self, thesis: str, context: str | None = None) -> list[str]:
        """Extract key concepts and terms.

        Args:
            thesis: The thesis statement
            context: Additional context

        Returns:
            List of key concepts
        """
        concepts = []
        combined_text = thesis
        if context:
            combined_text += " " + context

        # Extract quoted terms
        quoted_pattern = r'"([^"]+)"'
        matches = re.findall(quoted_pattern, combined_text)
        concepts.extend(matches)

        # Extract capitalized multi-word terms (likely proper nouns or concepts)
        cap_pattern = r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"
        matches = re.findall(cap_pattern, combined_text)
        concepts.extend(matches)

        # Extract important terms from the thesis
        important_terms = [
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "neural networks",
            "ethics",
            "autonomous vehicles",
            "decision-making",
            "algorithms",
            "regulatory",
            "frameworks",
            "moral",
            "liability",
            "trolley problem",
            "cultural differences",
        ]
        for term in important_terms:
            if term.lower() in combined_text.lower():
                concepts.append(term)

        # Extract terms with specific patterns
        term_patterns = [
            r"\b(\w+\s+theory)\b",
            r"\b(\w+\s+model)\b",
            r"\b(\w+\s+framework)\b",
            r"\b(\w+\s+frameworks?)\b",  # Also match "frameworks"
            r"\b(\w+\s+approach)\b",
            r"\b(\w+\s+method)\b",
            r"\b(\w+\s+algorithms?)\b",  # Also match "algorithms"
            r"\b(\w+\s+systems?)\b",
            r"\b(\w+\s+analysis)\b",
            r"\b(\w+\s+challenges?)\b",
        ]

        for pattern in term_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            concepts.extend(matches)

        # Deduplicate and clean
        seen = set()
        unique_concepts = []
        for concept in concepts:
            cleaned = concept.strip()
            MIN_CONCEPT_LENGTH = 3
            if cleaned.lower() not in seen and len(cleaned) > MIN_CONCEPT_LENGTH:
                seen.add(cleaned.lower())
                unique_concepts.append(cleaned)

        return unique_concepts[:10]  # Limit to 10 concepts

    def _determine_scope(self, thesis: str, context: str | None = None) -> str:
        """Determine the scope of research.

        Args:
            thesis: The thesis statement
            context: Additional context

        Returns:
            Scope description
        """
        combined_text = thesis.lower()
        if context:
            combined_text += " " + context.lower()

        # Check for scope indicators
        if any(word in combined_text for word in ["comprehensive", "extensive", "broad"]):
            return "broad"
        if any(word in combined_text for word in ["specific", "focused", "narrow"]):
            return "focused"
        if any(word in combined_text for word in ["exploratory", "preliminary"]):
            return "exploratory"
        if any(word in combined_text for word in ["comparative", "comparison"]):
            return "comparative"
        if any(word in combined_text for word in ["case study", "single case"]):
            return "case_study"
        # Default based on thesis length and complexity
        THESIS_COMPLEXITY_THRESHOLD_DEFAULT = 50
        if len(thesis.split()) > THESIS_COMPLEXITY_THRESHOLD_DEFAULT:
            return "broad"
        return "focused"

    def _extract_methodology_hints(self, thesis: str, context: str | None = None) -> list[str]:
        """Extract hints about methodology.

        Args:
            thesis: The thesis statement
            context: Additional context

        Returns:
            List of methodology hints
        """
        hints = []
        combined_text = thesis.lower()
        if context:
            combined_text += " " + context.lower()

        # Common methodology keywords
        methodology_keywords = {
            "quantitative": ["quantitative", "statistical", "measure", "survey", "experiment"],
            "qualitative": ["qualitative", "interview", "observation", "thematic", "narrative"],
            "mixed methods": ["both quantitative and qualitative", "mixed approach"],
            "systematic review": ["systematic review", "meta-analysis"],
            "case study": ["case study", "in-depth analysis"],
            "experimental": ["experiment", "control group", "hypothesis testing"],
            "descriptive": ["descriptive", "characterize", "profile"],
        }

        for method, keywords in methodology_keywords.items():
            if any(keyword in combined_text for keyword in keywords):
                hints.append(method)

        return hints
