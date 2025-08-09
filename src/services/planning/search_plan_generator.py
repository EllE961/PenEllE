"""Search plan generator for creating sourcing queries."""

import json

from src.core.llm import LLMClient
from src.core.logging.structured import get_logger

from .models import DocumentSection, SearchFilter, SearchPlan, SearchQuery, ThesisAnalysis

logger = get_logger(__name__)


class SearchPlanGenerator:
    """Generates search plans for the sourcing stage."""

    def __init__(self, use_llm: bool = True):
        """Initialize search plan generator."""
        self.query_templates = self._init_query_templates()
        self.use_llm = use_llm
        if use_llm:
            from src.core.config.loader import load_config

            pipeline_dict = load_config("pipeline")
            model_name = pipeline_dict.get("default_models", {}).get("research", "ollama-mixtral")
            self.llm = LLMClient(model_name=model_name)

    async def generate(
        self,
        analysis: ThesisAnalysis,
        sections: list[DocumentSection],
        keywords: list[str] | None = None,
        constraints: dict | None = None,
    ) -> SearchPlan:
        """Generate search plan based on analysis and sections.

        Args:
            analysis: Thesis analysis results
            sections: Document sections
            keywords: Additional keywords
            constraints: Search constraints

        Returns:
            Search plan with queries and filters
        """
        logger.info(
            "Generating search plan",
            num_sections=len(sections),
            has_keywords=bool(keywords),
            has_constraints=bool(constraints),
        )

        # Generate queries
        if self.use_llm:
            queries = await self._generate_queries_with_llm(analysis, sections, keywords)
        else:
            queries = self._generate_queries(analysis, sections, keywords)

        # Generate filters
        filters = self._generate_filters(analysis, constraints)

        # Calculate expected sources
        total_expected = self._calculate_expected_sources(sections)

        # Determine search strategy
        strategy = self._determine_strategy(analysis, len(sections))

        search_plan = SearchPlan(
            queries=queries,
            filters=filters,
            total_expected_sources=total_expected,
            search_strategy=strategy,
            metadata={
                "thesis_scope": analysis.scope,
                "num_sections": len(sections),
                "num_concepts": len(analysis.key_concepts),
            },
        )

        logger.info(
            "Search plan generated",
            num_queries=len(queries),
            num_filters=len(filters),
            expected_sources=total_expected,
        )

        return search_plan

    async def _generate_queries_with_llm(
        self,
        analysis: ThesisAnalysis,
        sections: list[DocumentSection],
        keywords: list[str] | None = None,
    ) -> list[SearchQuery]:
        """Generate search queries using LLM."""
        system_prompt = """You are an expert research librarian. Generate effective search queries for academic research.

        Return a JSON array of search queries with this structure:
        [
            {
                "query": "The actual search query string",
                "purpose": "What this query aims to find",
                "expected_results": 10,
                "priority": 1
            }
        ]

        Guidelines:
        1. Create specific, targeted queries
        2. Use academic search operators (AND, OR, NOT, quotes for phrases)
        3. Include both broad and specific queries
        4. Priority 1 is highest, 5 is lowest
        5. Generate 10-20 queries total"""

        sections_info = "\n".join(
            [f"- {s.title}: {s.description} ({s.word_budget} words)" for s in sections[:5]]
        )

        user_prompt = f"""Generate search queries for this research:

        Topic: {analysis.main_topic}
        Key Concepts: {', '.join(analysis.key_concepts[:8])}
        Research Questions: {'; '.join(analysis.research_questions[:3])}

        Document Sections:
        {sections_info}

        Additional Keywords: {', '.join(keywords) if keywords else 'None'}"""

        try:
            response = await self.llm.generate(
                prompt=user_prompt, system=system_prompt, temperature=0.5, max_tokens=1500
            )

            # Parse JSON response
            try:
                json_start = response.find("[")
                json_end = response.rfind("]") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    queries_data = json.loads(json_str)
                else:
                    raise ValueError("No JSON array found in response")

                queries = []
                for query_data in queries_data[:20]:  # Limit to 20 queries
                    query = SearchQuery(
                        query=query_data.get("query", ""),
                        purpose=query_data.get("purpose", "General search"),
                        expected_results=query_data.get("expected_results", 10),
                        priority=query_data.get("priority", 3),
                    )
                    if query.query:  # Only add non-empty queries
                        queries.append(query)

                logger.info("Generated search queries with LLM", num_queries=len(queries))

                return queries

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "Failed to parse LLM search queries, falling back to heuristics", error=str(e)
                )
                return self._generate_queries(analysis, sections, keywords)

        except Exception:
            logger.exception("LLM query generation failed, falling back to heuristics")
            return self._generate_queries(analysis, sections, keywords)

    def _generate_queries(
        self,
        analysis: ThesisAnalysis,
        sections: list[DocumentSection],
        keywords: list[str] | None = None,
    ) -> list[SearchQuery]:
        """Generate search queries.

        Args:
            analysis: Thesis analysis results
            sections: Document sections
            keywords: Additional keywords

        Returns:
            List of search queries
        """
        queries = []
        seen_queries: set[str] = set()

        # Primary query from main topic
        primary_query = self._create_primary_query(analysis.main_topic)
        queries.append(primary_query)
        seen_queries.add(primary_query.query.lower())

        # Queries for research questions
        for i, question in enumerate(analysis.research_questions[:3]):
            query_text = self._question_to_query(question)
            if query_text.lower() not in seen_queries:
                queries.append(
                    SearchQuery(
                        query=query_text,
                        purpose=f"Research question {i + 1}",
                        expected_results=10,
                        priority=2,
                    )
                )
                seen_queries.add(query_text.lower())

        # Queries for key concepts
        for concept in analysis.key_concepts[:5]:
            query_text = f'"{concept}" research OR study OR analysis'
            if query_text.lower() not in seen_queries:
                queries.append(
                    SearchQuery(
                        query=query_text,
                        purpose=f"Key concept: {concept}",
                        expected_results=8,
                        priority=3,
                    )
                )
                seen_queries.add(query_text.lower())

        # Section-specific queries
        for section in sections:
            section_queries = self._generate_section_queries(section, analysis)
            for sq in section_queries:
                if sq.query.lower() not in seen_queries:
                    queries.append(sq)
                    seen_queries.add(sq.query.lower())

        # Keyword queries
        if keywords:
            for keyword in keywords[:5]:
                query_text = f"{keyword} {analysis.main_topic}"
                if query_text.lower() not in seen_queries:
                    queries.append(
                        SearchQuery(
                            query=query_text,
                            purpose=f"Keyword: {keyword}",
                            expected_results=5,
                            priority=4,
                        )
                    )
                    seen_queries.add(query_text.lower())

        # Sort by priority
        queries.sort(key=lambda q: q.priority)

        return queries[:20]  # Limit to 20 queries

    def _create_primary_query(self, main_topic: str) -> SearchQuery:
        """Create primary search query.

        Args:
            main_topic: Main topic from analysis

        Returns:
            Primary search query
        """
        # Clean and enhance the main topic
        enhanced_query = f"{main_topic} research study analysis"

        return SearchQuery(
            query=enhanced_query,
            purpose="Primary topic search",
            expected_results=20,
            priority=1,
        )

    def _question_to_query(self, question: str) -> str:
        """Convert research question to search query.

        Args:
            question: Research question

        Returns:
            Search query
        """
        # Remove question marks and common question words
        query = question.replace("?", "")
        question_words = ["how", "what", "why", "when", "where", "who", "which"]

        for word in question_words:
            if query.lower().startswith(word):
                query = query[len(word) :].strip()

        return query

    def _generate_section_queries(
        self, section: DocumentSection, analysis: ThesisAnalysis
    ) -> list[SearchQuery]:
        """Generate queries for a specific section.

        Args:
            section: Document section
            analysis: Thesis analysis

        Returns:
            List of search queries
        """
        queries = []
        section_lower = section.title.lower()

        # Use templates based on section type
        if "literature" in section_lower or "review" in section_lower:
            # Literature review queries
            queries.append(
                SearchQuery(
                    query=f"{analysis.main_topic} systematic review meta-analysis",
                    purpose=f"{section.title}: Reviews",
                    expected_results=10,
                    priority=2,
                )
            )
            queries.append(
                SearchQuery(
                    query=f"{analysis.main_topic} theoretical framework",
                    purpose=f"{section.title}: Theories",
                    expected_results=8,
                    priority=3,
                )
            )

        elif "methodology" in section_lower:
            # Methodology queries
            if analysis.methodology_hints:
                for hint in analysis.methodology_hints[:2]:
                    queries.append(
                        SearchQuery(
                            query=f"{hint} methodology {analysis.main_topic}",
                            purpose=f"{section.title}: {hint}",
                            expected_results=5,
                            priority=3,
                        )
                    )

        elif "result" in section_lower or "finding" in section_lower:
            # Results queries
            queries.append(
                SearchQuery(
                    query=f"{analysis.main_topic} empirical findings results",
                    purpose=f"{section.title}: Empirical studies",
                    expected_results=10,
                    priority=2,
                )
            )

        # Add queries based on key points
        for point in section.key_points[:2]:
            if "concept:" in point.lower():
                concept = point.split(":")[-1].strip()
                queries.append(
                    SearchQuery(
                        query=f'"{concept}" definition theory',
                        purpose=f"{section.title}: {concept}",
                        expected_results=5,
                        priority=4,
                    )
                )

        return queries

    def _generate_filters(
        self, analysis: ThesisAnalysis, constraints: dict | None = None
    ) -> list[SearchFilter]:
        """Generate search filters.

        Args:
            analysis: Thesis analysis results
            constraints: Search constraints

        Returns:
            List of search filters
        """
        filters = []

        # Date filter - prefer recent research
        filters.append(
            SearchFilter(
                field="publication_date",
                operator="gte",
                value="2018-01-01",  # Last 5 years
            )
        )

        # Language filter
        filters.append(SearchFilter(field="language", operator="eq", value="en"))

        # Document type filters based on scope
        if analysis.scope in ["broad", "comprehensive"]:
            # Include more document types
            filters.append(
                SearchFilter(
                    field="document_type",
                    operator="in",
                    value=["article", "review", "book", "dissertation"],
                )
            )
        else:
            # Focus on peer-reviewed articles
            filters.append(
                SearchFilter(
                    field="document_type",
                    operator="in",
                    value=["article", "review"],
                )
            )

        # Add constraint-based filters
        if constraints:
            if "excluded_sources" in constraints:
                for source in constraints["excluded_sources"]:
                    filters.append(SearchFilter(field="doi", operator="ne", value=source))

            if "publication_years" in constraints:
                years = constraints["publication_years"]
                if "min" in years:
                    filters.append(
                        SearchFilter(
                            field="publication_year",
                            operator="gte",
                            value=years["min"],
                        )
                    )
                if "max" in years:
                    filters.append(
                        SearchFilter(
                            field="publication_year",
                            operator="lte",
                            value=years["max"],
                        )
                    )

        return filters

    def _calculate_expected_sources(self, sections: list[DocumentSection]) -> int:
        """Calculate total expected sources.

        Args:
            sections: Document sections

        Returns:
            Total expected sources
        """
        # Base calculation: 5-10 sources per major section
        base_per_section = 7

        # Count major sections (exclude subsections)
        major_sections = [s for s in sections if s.parent_section_id is None]

        # Calculate total
        total = len(major_sections) * base_per_section

        # Adjust based on word count
        total_words = sum(s.word_budget for s in sections)
        LONG_DOCUMENT_THRESHOLD = 5000
        SHORT_DOCUMENT_THRESHOLD = 2000
        if total_words > LONG_DOCUMENT_THRESHOLD:
            total = int(total * 1.2)  # 20% more for longer documents
        elif total_words < SHORT_DOCUMENT_THRESHOLD:
            total = int(total * 0.8)  # 20% less for shorter documents

        return max(20, min(total, 100))  # Between 20 and 100 sources

    def _determine_strategy(self, analysis: ThesisAnalysis, num_sections: int) -> str:
        """Determine search strategy.

        Args:
            analysis: Thesis analysis results
            num_sections: Number of sections

        Returns:
            Search strategy name
        """
        MANY_SECTIONS_THRESHOLD = 6
        if analysis.scope == "broad" or num_sections > MANY_SECTIONS_THRESHOLD:
            return "comprehensive"
        if analysis.scope == "focused":
            return "targeted"
        if analysis.scope == "exploratory":
            return "exploratory"
        return "balanced"

    def _init_query_templates(self) -> dict[str, list[str]]:
        """Initialize query templates.

        Returns:
            Dictionary of query templates by type
        """
        return {
            "definition": [
                '"{term}" definition meaning',
                '"{term}" "is defined as"',
                'what is "{term}"',
            ],
            "theory": [
                '"{term}" theory framework',
                '"{term}" theoretical perspective',
                '"{term}" model approach',
            ],
            "empirical": [
                '"{term}" empirical study research',
                '"{term}" findings results data',
                '"{term}" evidence analysis',
            ],
            "review": [
                '"{term}" systematic review',
                '"{term}" literature review',
                '"{term}" meta-analysis',
            ],
            "methodology": [
                '"{term}" methodology method',
                '"{term}" research design',
                '"{term}" data collection analysis',
            ],
        }
