"""FastAPI dependencies for request validation."""

import json
from typing import Any, Callable, Dict, Type

from fastapi import HTTPException, Request
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from .registry import SchemaRegistry
from .validation_service import ValidationService

validation_service = ValidationService()
schema_registry = SchemaRegistry()


def validate_request(schema_name: str) -> Callable:
    """
    Dependency to validate request body against a schema.

    Args:
        schema_name: Name of the schema to validate against

    Returns:
        FastAPI dependency function

    Raises:
        HTTPException: If validation fails
    """

    async def _validate(request: Request) -> Dict[str, Any]:
        """Inner validation function."""
        try:
            # Get request body
            body = await request.json()

            # Validate against schema
            result = validation_service.validate(body, schema_name)  # type: ignore[arg-type]

            if not result.is_valid:
                # Format error details
                errors = []
                for error in result.errors:
                    errors.append(
                        {
                            "path": error.path,
                            "message": error.message,
                            "value": getattr(error, "value", None),
                        }
                    )

                raise HTTPException(
                    status_code=422, detail={"message": "Validation failed", "errors": errors}
                )

            return body  # type: ignore[no-any-return]

        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400, detail={"message": "Invalid JSON", "error": str(e)}
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail={"message": "Internal validation error", "error": str(e)}
            )

    return _validate


def validate_model(model: Type[BaseModel]) -> Callable:
    """
    Dependency to validate request body against a Pydantic model.

    Args:
        model: Pydantic model class to validate against

    Returns:
        FastAPI dependency function
    """

    async def _validate(request: Request) -> BaseModel:
        """Inner validation function."""
        try:
            # Get request body
            body = await request.json()

            # Validate and create model instance
            return model(**body)

        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400, detail={"message": "Invalid JSON", "error": str(e)}
            )
        except PydanticValidationError as e:
            # Format Pydantic errors
            errors = []
            for error in e.errors():
                errors.append(
                    {
                        "path": ".".join(str(p) for p in error["loc"]),
                        "message": error["msg"],
                        "type": error["type"],
                    }
                )

            raise HTTPException(
                status_code=422, detail={"message": "Validation failed", "errors": errors}
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail={"message": "Internal validation error", "error": str(e)}
            )

    return _validate


def get_validation_service() -> ValidationService:
    """Get the validation service instance."""
    return validation_service


def get_schema_registry() -> SchemaRegistry:
    """Get the schema registry instance."""
    return schema_registry


# Example usage in FastAPI routes:
"""
from fastapi import APIRouter, Depends
from src.core.schemas.dependencies import validate_request, validate_model
from src.core.schemas.models import RunConfiguration, Source

router = APIRouter()

@router.post("/validate/run-config")
async def validate_run_config(
    data: Dict[str, Any] = Depends(validate_request("run_configuration"))
):
    # Data is already validated
    return {"status": "valid", "data": data}

@router.post("/validate/source")
async def validate_source_model(
    source: Source = Depends(validate_model(Source))
):
    # Source is validated and parsed as Pydantic model
    return {"status": "valid", "source": source.dict()}
"""
