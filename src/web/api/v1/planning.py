"""Planning API endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from ....core.events.bus import EventBus, get_event_bus
from ....core.logging.structured import get_logger
from ....core.storage import SimpleArtifactStore as ArtifactStore
from ....core.storage import get_artifact_store
from ....services.planning import PlanningService, PlanRequest, PlanResponse

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/v1/planning", tags=["planning"])


def get_planning_service(
    artifact_store: ArtifactStore = Depends(get_artifact_store),
    event_bus: EventBus = Depends(get_event_bus),
) -> PlanningService:
    """Get planning service instance.

    Args:
        artifact_store: Artifact store dependency
        event_bus: Event bus dependency

    Returns:
        Planning service instance
    """
    return PlanningService(artifact_store=artifact_store, event_bus=event_bus)


@router.post("/plan", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: PlanRequest,
    planning_service: PlanningService = Depends(get_planning_service),
) -> PlanResponse:
    """Create a new document plan.

    Args:
        request: Planning request
        planning_service: Planning service dependency

    Returns:
        Planning response with sections and search plan
    """
    try:
        logger.info(
            "Received planning request",
            thesis_length=len(request.thesis),
            target_words=request.target_word_count,
        )

        # Generate plan
        response = await planning_service.plan(request)

        logger.info(
            "Plan created successfully",
            plan_id=response.plan_id,
            num_sections=len(response.sections),
        )

        return response

    except ValueError as e:
        logger.error("Invalid planning request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Planning failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Planning failed. Please try again.",
        )


@router.get("/plan/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: str,
    artifact_store: ArtifactStore = Depends(get_artifact_store),
) -> PlanResponse:
    """Get an existing plan by ID.

    Args:
        plan_id: Plan ID
        artifact_store: Artifact store dependency

    Returns:
        Planning response
    """
    try:
        logger.info("Retrieving plan", plan_id=plan_id)

        # Get plan from artifact store
        plan_data = await artifact_store.get(plan_id, "plan")

        if not plan_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan {plan_id} not found",
            )

        # Parse and return plan
        response = PlanResponse(**plan_data)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve plan", plan_id=plan_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve plan",
        )


@router.put("/plan/{plan_id}/refine", response_model=PlanResponse)
async def refine_plan(
    plan_id: str,
    refinements: Dict,
    planning_service: PlanningService = Depends(get_planning_service),
) -> PlanResponse:
    """Refine an existing plan.

    Args:
        plan_id: Plan ID
        refinements: Refinement instructions
        planning_service: Planning service dependency

    Returns:
        Updated planning response
    """
    try:
        logger.info("Refining plan", plan_id=plan_id)

        # Refine plan
        response = await planning_service.refine_plan(plan_id, refinements)

        logger.info("Plan refined successfully", plan_id=plan_id)

        return response

    except ValueError as e:
        logger.error("Invalid refinement request", plan_id=plan_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Plan refinement failed", plan_id=plan_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Plan refinement failed",
        )


@router.post("/plan/validate")
async def validate_plan_request(request: PlanRequest) -> Dict[str, Any]:
    """Validate a planning request without creating a plan.

    Args:
        request: Planning request to validate

    Returns:
        Validation result
    """
    try:
        # Basic validation (Pydantic handles most of it)
        is_valid = True
        errors = []

        # Check thesis complexity
        if len(request.thesis.split()) < 5:
            is_valid = False
            errors.append("Thesis too short (minimum 5 words)")

        # Check word count feasibility
        if request.target_word_count < 500:
            is_valid = False
            errors.append("Target word count too low (minimum 500)")

        # Check outline consistency
        if request.outline:
            total_outlined_words = sum(
                section.get("target_word_count", 0)
                for section in request.outline
                if "target_word_count" in section
            )
            if total_outlined_words > request.target_word_count * 1.2:
                is_valid = False
                errors.append("Outlined sections exceed target word count")

        return {
            "valid": is_valid,
            "errors": errors,
        }

    except Exception as e:
        logger.error("Validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Validation failed",
        )


@router.get("/templates/{document_type}")
async def get_document_template(document_type: str) -> Dict:
    """Get a document template for a specific type.

    Args:
        document_type: Type of document

    Returns:
        Document template
    """
    templates = {
        "research_paper": {
            "sections": [
                {"title": "Introduction", "weight": 0.15},
                {"title": "Literature Review", "weight": 0.25},
                {"title": "Methodology", "weight": 0.15},
                {"title": "Results", "weight": 0.2},
                {"title": "Discussion", "weight": 0.15},
                {"title": "Conclusion", "weight": 0.1},
            ],
            "min_word_count": 3000,
            "max_word_count": 10000,
        },
        "essay": {
            "sections": [
                {"title": "Introduction", "weight": 0.15},
                {"title": "Main Arguments", "weight": 0.6},
                {"title": "Counter-arguments", "weight": 0.15},
                {"title": "Conclusion", "weight": 0.1},
            ],
            "min_word_count": 1000,
            "max_word_count": 5000,
        },
        "literature_review": {
            "sections": [
                {"title": "Introduction", "weight": 0.1},
                {"title": "Theoretical Background", "weight": 0.2},
                {"title": "Thematic Analysis", "weight": 0.5},
                {"title": "Gaps and Opportunities", "weight": 0.1},
                {"title": "Conclusion", "weight": 0.1},
            ],
            "min_word_count": 2000,
            "max_word_count": 8000,
        },
    }

    if document_type not in templates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template for document type '{document_type}' not found",
        )

    return templates[document_type]
