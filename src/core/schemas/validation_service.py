"""Centralized validation service for PenEllE schemas."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Union

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .validators.base import ValidationError, ValidationResult, ValidationSeverity
from .validators.claim_validator import ClaimValidator
from .validators.evidence_validator import EvidenceValidator
from .validators.output_validator import (
    DraftSectionValidator,
    QualityReportValidator,
    RunManifestValidator,
)
from .validators.run_validator import RunIntakeValidator, RunValidator
from .validators.source_validator import SourceValidator

# Configure logging
logger = logging.getLogger(__name__)


class ValidationRequest(BaseModel):
    """Request model for validation API."""

    schema_type: str = Field(..., description="Type of schema to validate against")
    data: Dict[str, Any] = Field(..., description="Data to validate")
    strict_mode: bool = Field(True, description="Treat warnings as errors")
    options: Dict[str, Any] = Field(
        default_factory=dict, description="Additional validation options"
    )


class ValidationResponse(BaseModel):
    """Response model for validation API."""

    is_valid: bool
    errors: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    validated_at: str


class ValidationService:
    """
    Centralized service for validating PenEllE data against schemas.

    This service provides:
    - Unified interface for all validators
    - FastAPI integration
    - Batch validation support
    - Caching of validators
    - Detailed error reporting
    """

    # Map schema types to validator classes
    VALIDATOR_MAP = {
        "run_configuration": RunValidator,
        "run_intake": RunIntakeValidator,
        "source": SourceValidator,
        "evidence": EvidenceValidator,
        "evidence_limited": lambda: EvidenceValidator(evidence_type="limited_access"),
        "claim": ClaimValidator,
        "draft_section": DraftSectionValidator,
        "quality_report": QualityReportValidator,
        "run_manifest": RunManifestValidator,
    }

    def __init__(self, cache_validators: bool = True):
        """
        Initialize validation service.

        Args:
            cache_validators: If True, cache validator instances
        """
        self.cache_validators = cache_validators
        self._validator_cache: Dict[str, Any] = {}

        # Load available schemas
        self.available_schemas = self._load_available_schemas()

    def _load_available_schemas(self) -> List[str]:
        """Load list of available schema types."""
        return list(self.VALIDATOR_MAP.keys())

    def _get_validator(self, schema_type: str, strict_mode: bool = True) -> Any:
        """
        Get or create a validator instance.

        Args:
            schema_type: Type of schema to validate
            strict_mode: Whether to use strict validation

        Returns:
            Validator instance

        Raises:
            ValueError: If schema type is not supported
        """
        if schema_type not in self.VALIDATOR_MAP:
            raise ValueError(
                f"Unsupported schema type '{schema_type}'. "
                f"Available types: {', '.join(self.available_schemas)}"
            )

        # Create cache key
        cache_key = f"{schema_type}_{strict_mode}"

        # Check cache
        if self.cache_validators and cache_key in self._validator_cache:
            return self._validator_cache[cache_key]

        # Create validator
        validator_class = self.VALIDATOR_MAP[schema_type]
        if callable(validator_class) and not isinstance(validator_class, type):
            # Handle lambda functions
            validator = validator_class()
        else:
            # Handle regular classes
            validator = validator_class(strict_mode=strict_mode)  # type: ignore[operator]

        # Cache if enabled
        if self.cache_validators:
            self._validator_cache[cache_key] = validator

        return validator

    def validate(
        self,
        schema_type: str,
        data: Dict[str, Any],
        strict_mode: bool = True,
        **options: Any,
    ) -> ValidationResult:
        """
        Validate data against a schema.

        Args:
            schema_type: Type of schema to validate against
            data: Data to validate
            strict_mode: If True, treat warnings as errors
            **options: Additional validation options

        Returns:
            ValidationResult object

        Raises:
            ValueError: If schema type is not supported
        """
        logger.info(f"Validating data against schema type: {schema_type}")

        try:
            # Get validator
            validator = self._get_validator(schema_type, strict_mode)

            # Perform validation
            result = validator.validate(data)

            # Add metadata
            result.metadata["schema_type"] = schema_type
            result.metadata["validator_class"] = validator.__class__.__name__

            # Log results
            if result.is_valid:
                logger.info(f"Validation successful for {schema_type}")
            else:
                logger.warning(
                    f"Validation failed for {schema_type}: "
                    f"{len(result.errors)} errors, {len(result.warnings)} warnings"
                )

            return result  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(f"Validation error for {schema_type}: {str(e)}")
            raise

    def validate_batch(
        self,
        schema_type: str,
        data_list: List[Dict[str, Any]],
        strict_mode: bool = True,
        **options: Any,
    ) -> List[ValidationResult]:
        """
        Validate multiple data items against the same schema.

        Args:
            schema_type: Type of schema to validate against
            data_list: List of data items to validate
            strict_mode: If True, treat warnings as errors
            **options: Additional validation options

        Returns:
            List of ValidationResult objects
        """
        logger.info(f"Batch validating {len(data_list)} items against {schema_type}")

        # Get validator once
        validator = self._get_validator(schema_type, strict_mode)

        # Validate all items
        results = []
        for i, data in enumerate(data_list):
            try:
                result = validator.validate(data)
                result.metadata["batch_index"] = i
                result.metadata["schema_type"] = schema_type
                results.append(result)
            except Exception as e:
                logger.error(f"Batch validation error at index {i}: {str(e)}")
                # Create error result
                error_result = ValidationResult(
                    is_valid=False,
                    errors=[
                        ValidationError(
                            path="$",
                            message=f"Validation exception: {str(e)}",
                            severity=ValidationSeverity.ERROR,
                        )
                    ],
                    metadata={"batch_index": i, "schema_type": schema_type},
                )
                results.append(error_result)

        return results

    def validate_file(
        self,
        schema_type: str,
        file_path: Union[str, Path],
        strict_mode: bool = True,
        **options: Any,
    ) -> ValidationResult:
        """
        Validate JSON file contents against a schema.

        Args:
            schema_type: Type of schema to validate against
            file_path: Path to JSON file
            strict_mode: If True, treat warnings as errors
            **options: Additional validation options

        Returns:
            ValidationResult object
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.suffix == ".json":
            raise ValueError(f"File must be JSON: {file_path}")

        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            # Create validation result for JSON error
            return ValidationResult(
                is_valid=False,
                errors=[
                    ValidationError(
                        path="$",
                        message=f"Invalid JSON: {str(e)}",
                        severity=ValidationSeverity.ERROR,
                    )
                ],
                metadata={"file_path": str(file_path), "schema_type": schema_type},
            )

        # Validate data
        result = self.validate(schema_type, data, strict_mode, **options)
        result.metadata["file_path"] = str(file_path)

        return result

    def get_schema_info(self, schema_type: str) -> Dict[str, Any]:
        """
        Get information about a schema type.

        Args:
            schema_type: Type of schema

        Returns:
            Dictionary with schema information
        """
        if schema_type not in self.VALIDATOR_MAP:
            raise ValueError(f"Unknown schema type: {schema_type}")

        validator = self._get_validator(schema_type)

        return {
            "schema_type": schema_type,
            "validator_class": validator.__class__.__name__,
            "schema_path": str(validator.schema_path) if validator.schema_path else None,
            "has_custom_validation": hasattr(validator, "_custom_validate"),
            "description": (
                validator.__class__.__doc__.strip() if validator.__class__.__doc__ else None
            ),
        }

    def list_schemas(self) -> List[Dict[str, str]]:
        """
        List all available schema types.

        Returns:
            List of schema information dictionaries
        """
        schemas = []
        for schema_type in self.available_schemas:
            try:
                info = self.get_schema_info(schema_type)
                schemas.append(
                    {
                        "type": schema_type,
                        "description": info.get("description", ""),
                        "validator": info.get("validator_class", ""),
                    }
                )
            except Exception as e:
                logger.error(f"Error getting info for {schema_type}: {str(e)}")
                schemas.append(
                    {
                        "type": schema_type,
                        "description": "Error loading schema info",
                        "validator": "Unknown",
                    }
                )

        return schemas


# FastAPI integration functions
def create_validation_endpoint(validation_service: ValidationService) -> Any:
    """
    Create a FastAPI endpoint for validation.

    Args:
        validation_service: ValidationService instance

    Returns:
        Async function for FastAPI route
    """

    async def validate_endpoint(request: ValidationRequest) -> ValidationResponse:
        """Validate data against PenEllE schema."""
        try:
            # Perform validation
            result = validation_service.validate(
                schema_type=request.schema_type,
                data=request.data,
                strict_mode=request.strict_mode,
                **request.options,
            )

            # Convert to response
            return ValidationResponse(
                is_valid=result.is_valid,
                errors=[e.to_dict() for e in result.errors],
                warnings=[w.to_dict() for w in result.warnings],
                metadata=result.metadata,
                validated_at=result.validated_at.isoformat(),
            )

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Validation endpoint error: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal validation error")

    return validate_endpoint


def create_batch_validation_endpoint(validation_service: ValidationService) -> Any:
    """
    Create a FastAPI endpoint for batch validation.

    Args:
        validation_service: ValidationService instance

    Returns:
        Async function for FastAPI route
    """

    async def batch_validate_endpoint(
        schema_type: str, data_list: List[Dict[str, Any]], strict_mode: bool = True
    ) -> List[ValidationResponse]:
        """Batch validate data against PenEllE schema."""
        try:
            # Perform batch validation
            results = validation_service.validate_batch(
                schema_type=schema_type, data_list=data_list, strict_mode=strict_mode
            )

            # Convert to responses
            return [
                ValidationResponse(
                    is_valid=result.is_valid,
                    errors=[e.to_dict() for e in result.errors],
                    warnings=[w.to_dict() for w in result.warnings],
                    metadata=result.metadata,
                    validated_at=result.validated_at.isoformat(),
                )
                for result in results
            ]

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Batch validation endpoint error: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal validation error")

    return batch_validate_endpoint


# Singleton instance for easy import
validation_service = ValidationService()


# Convenience functions
def validate(schema_type: str, data: Dict[str, Any], **kwargs: Any) -> ValidationResult:
    """Convenience function for validation."""
    return validation_service.validate(schema_type, data, **kwargs)


def validate_batch(
    schema_type: str, data_list: List[Dict[str, Any]], **kwargs: Any
) -> List[ValidationResult]:
    """Convenience function for batch validation."""
    return validation_service.validate_batch(schema_type, data_list, **kwargs)


def validate_file(schema_type: str, file_path: Union[str, Path], **kwargs: Any) -> ValidationResult:
    """Convenience function for file validation."""
    return validation_service.validate_file(schema_type, file_path, **kwargs)
