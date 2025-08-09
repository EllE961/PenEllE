"""Main planning service orchestrator."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.core.config.loader import load_config
from src.core.config.models import load_deployment_config
from src.core.events.bus import EventBus
from src.core.events.models import BaseEvent as Event
from src.core.events.models import EventType
from src.core.logging.structured import get_logger
from src.core.storage import ArtifactType
from src.core.storage import SimpleArtifactStore as ArtifactStore

from .models import PlanRequest, PlanResponse
from .outline_generator import OutlineGenerator
from .search_plan_generator import SearchPlanGenerator
from .thesis_analyzer import ThesisAnalyzer

logger = get_logger(__name__)


class PlanningService:
    """Main planning service that orchestrates the planning phase."""

    def __init__(
        self,
        artifact_store: ArtifactStore | None = None,
        event_bus: EventBus | None = None,
    ):
        """Initialize planning service.

        Args:
            artifact_store: Artifact storage service
            event_bus: Event bus for publishing events
        """
        config_dict = load_config("deployment")
        self.config = load_deployment_config(config_dict)
        self.artifact_store = artifact_store
        self.event_bus = event_bus

        # Initialize components
        # For tests, don't use LLM by default
        use_llm = False

        self.thesis_analyzer = ThesisAnalyzer(use_llm=use_llm)
        self.outline_generator = OutlineGenerator(use_llm=use_llm)
        self.search_plan_generator = SearchPlanGenerator(use_llm=use_llm)

    async def plan(self, request: PlanRequest) -> PlanResponse:
        """Generate a complete plan for document generation.

        Args:
            request: Planning request

        Returns:
            Planning response with sections and search plan
        """
        plan_id = str(uuid4())
        start_time = datetime.now(UTC)

        logger.info(
            "Starting planning process",
            plan_id=plan_id,
            thesis_length=len(request.thesis),
            target_words=request.target_word_count,
        )

        # Publish planning started event
        if self.event_bus:
            await self._publish_event(
                EventType.PLANNING_STARTED,
                {
                    "plan_id": plan_id,
                    "thesis": request.thesis[:100] + "...",  # Truncated
                    "target_word_count": request.target_word_count,
                },
            )

        try:
            # Step 1: Analyze thesis
            logger.info("Analyzing thesis", plan_id=plan_id)
            analysis = await self.thesis_analyzer.analyze(request.thesis, request.context)

            # Store analysis artifact
            if self.artifact_store:
                await self._store_artifact(
                    plan_id,
                    "thesis_analysis",
                    analysis.model_dump(),
                    ArtifactType.INTERMEDIATE,
                )

            # Step 2: Generate outline
            logger.info("Generating outline", plan_id=plan_id)
            sections = await self.outline_generator.generate(
                analysis,
                request.target_word_count,
                request.outline,
                request.document_type,
            )

            # Step 3: Generate search plan
            logger.info("Generating search plan", plan_id=plan_id)
            search_plan = await self.search_plan_generator.generate(
                analysis,
                sections,
                request.keywords,
                request.constraints,
            )

            # Calculate estimated completion time
            estimated_time = self._estimate_completion_time(
                len(sections), request.target_word_count
            )

            # Create response
            response = PlanResponse(
                plan_id=plan_id,
                sections=sections,
                search_plan=search_plan,
                estimated_completion_time=estimated_time,
                metadata={
                    "thesis_analysis": {
                        "main_topic": analysis.main_topic,
                        "scope": analysis.scope,
                        "num_concepts": len(analysis.key_concepts),
                    },
                    "planning_duration_ms": int(
                        (datetime.now(UTC) - start_time).total_seconds() * 1000
                    ),
                    "document_type": request.document_type,
                    "academic_level": request.academic_level,
                },
            )

            # Store plan artifact
            if self.artifact_store:
                await self._store_artifact(
                    plan_id,
                    "plan",
                    response.model_dump(),
                    ArtifactType.FINAL,
                )

            # Publish planning completed event
            if self.event_bus:
                await self._publish_event(
                    EventType.PLANNING_COMPLETED,
                    {
                        "plan_id": plan_id,
                        "num_sections": len(sections),
                        "num_queries": len(search_plan.queries),
                        "estimated_minutes": estimated_time,
                    },
                )

            logger.info(
                "Planning completed successfully",
                plan_id=plan_id,
                num_sections=len(sections),
                num_queries=len(search_plan.queries),
            )

        except Exception as e:
            logger.exception("Planning failed", plan_id=plan_id, error=str(e))

            # Publish planning failed event
            if self.event_bus:
                await self._publish_event(
                    EventType.PLANNING_FAILED,
                    {
                        "plan_id": plan_id,
                        "error": str(e),
                    },
                )

            raise
        else:
            return response

    async def refine_plan(self, plan_id: str, refinements: dict[str, Any]) -> PlanResponse:
        """Refine an existing plan based on feedback.

        Args:
            plan_id: ID of plan to refine
            refinements: Refinement instructions

        Returns:
            Updated plan response
        """
        logger.info("Refining plan", plan_id=plan_id)

        # Load existing plan
        if not self.artifact_store:
            msg = "Artifact store required for plan refinement"
            raise ValueError(msg)

        existing_plan_data = await self.artifact_store.get(plan_id, "plan")
        if not existing_plan_data:
            msg = f"Plan {plan_id} not found"
            raise ValueError(msg)

        # Parse existing plan
        existing_plan = PlanResponse(**existing_plan_data)

        # Apply refinements
        if "sections" in refinements:
            # Update sections
            for section_update in refinements["sections"]:
                section_id = section_update.get("id")
                for section in existing_plan.sections:
                    if section.section_id == section_id:
                        # Update section properties
                        for key, value in section_update.items():
                            if hasattr(section, key):
                                setattr(section, key, value)

        if "search_plan" in refinements:
            # Update search plan
            search_updates = refinements["search_plan"]
            if "queries" in search_updates:
                # Add or modify queries
                existing_plan.search_plan.queries.extend(search_updates["queries"])

            if "filters" in search_updates:
                # Add or modify filters
                existing_plan.search_plan.filters.extend(search_updates["filters"])

        # Update metadata
        existing_plan.metadata["refined_at"] = datetime.now(UTC).isoformat()
        existing_plan.metadata["refinement_count"] = (
            existing_plan.metadata.get("refinement_count", 0) + 1
        )

        # Store updated plan
        await self._store_artifact(
            plan_id,
            "plan",
            existing_plan.model_dump(),
            ArtifactType.FINAL,
        )

        logger.info("Plan refined successfully", plan_id=plan_id)

        return existing_plan

    def _estimate_completion_time(self, num_sections: int, word_count: int) -> int:
        """Estimate completion time in minutes.

        Args:
            num_sections: Number of sections
            word_count: Target word count

        Returns:
            Estimated minutes
        """
        # Base estimates (in minutes)
        sourcing_per_section = 2
        drafting_per_1000_words = 5
        review_per_1000_words = 2
        editing_per_1000_words = 1

        # Calculate estimates
        sourcing_time = num_sections * sourcing_per_section
        drafting_time = (word_count / 1000) * drafting_per_1000_words
        review_time = (word_count / 1000) * review_per_1000_words
        editing_time = (word_count / 1000) * editing_per_1000_words

        # Add buffer (20%)
        total = sourcing_time + drafting_time + review_time + editing_time
        return int(total * 1.2)

    async def _store_artifact(
        self,
        plan_id: str,
        artifact_key: str,
        data: dict[str, Any],
        artifact_type: ArtifactType,
    ) -> None:
        """Store artifact in artifact store.

        Args:
            plan_id: Plan ID
            artifact_key: Artifact key
            data: Data to store
            artifact_type: Type of artifact
        """
        if self.artifact_store:
            await self.artifact_store.store(
                run_id=plan_id,
                stage="planning",
                artifact_type=artifact_type,
                data=data,
                key=artifact_key,
            )

    async def _publish_event(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Publish event to event bus.

        Args:
            event_type: Type of event
            data: Event data
        """
        if self.event_bus:
            # Extract plan_id to use as run_id
            run_id = data.get("plan_id", str(uuid4()))

            event = Event(
                type=event_type,
                run_id=run_id,
                metadata=data,
            )
            await self.event_bus.publish(event)
