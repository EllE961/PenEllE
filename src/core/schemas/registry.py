"""Schema Registry for JSON Schema validation and management."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from jsonschema import Draft7Validator, FormatChecker, ValidationError
from pydantic import BaseModel

from src.core.schemas.models import (
    Bibliography,
    Claim,
    DraftSection,
    EventEnvelope,
    Evidence,
    LimitedAccessEvidence,
    QualityReport,
    RunConfiguration,
    RunManifest,
    SearchResult,
    Source,
    StructuredInput,
)


class SchemaRegistry:
    """Central registry for managing JSON schemas and validation."""

    def __init__(self, schema_dir: Optional[Path] = None):
        """Initialize the schema registry.

        Args:
            schema_dir: Directory containing JSON schema files.
                       Defaults to src/core/schemas/json/
        """
        if schema_dir is None:
            schema_dir = Path(__file__).parent / "json"

        self.schema_dir = schema_dir
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._validators: Dict[str, Draft7Validator] = {}

        # Create format checker with uuid, date-time, and date
        self._format_checker = FormatChecker()
        self._format_checker.checks("uuid")(self._check_uuid)
        self._format_checker.checks("date-time")(self._check_datetime)
        self._format_checker.checks("date")(self._check_date)

        self._model_mapping: Dict[str, Type[BaseModel]] = {
            "source": Source,
            "evidence": Evidence,
            "claim": Claim,
            "draft_section": DraftSection,
            "run_manifest": RunManifest,
            "run_configuration": RunConfiguration,
            "quality_report": QualityReport,
            "event_envelope": EventEnvelope,
            "search_result": SearchResult,
            "bibliography": Bibliography,
            "structured_input": StructuredInput,
            "limited_access_evidence": LimitedAccessEvidence,
        }

        # Load all schemas on initialization
        self._load_all_schemas()

    def _check_uuid(self, instance: Any) -> bool:
        """Check if instance is a valid UUID."""
        from uuid import UUID

        try:
            UUID(instance)
            return True
        except (ValueError, TypeError):
            return False

    def _check_datetime(self, instance: Any) -> bool:
        """Check if instance is a valid ISO datetime."""
        from datetime import datetime

        try:
            # Try parsing as ISO format
            if instance.endswith("Z"):
                datetime.fromisoformat(instance[:-1] + "+00:00")
            else:
                datetime.fromisoformat(instance)
            return True
        except (ValueError, TypeError):
            return False

    def _check_date(self, instance: Any) -> bool:
        """Check if instance is a valid date."""
        from datetime import datetime

        try:
            # Try parsing as date format YYYY-MM-DD
            datetime.strptime(instance, "%Y-%m-%d")
            return True
        except (ValueError, TypeError):
            return False

    def _load_all_schemas(self) -> None:
        """Load all JSON schemas from the schema directory."""
        for schema_file in self.schema_dir.glob("*.json"):
            schema_name = schema_file.stem
            try:
                with open(schema_file, "r") as f:
                    schema = json.load(f)
                self._schemas[schema_name] = schema
                self._validators[schema_name] = Draft7Validator(
                    schema, format_checker=self._format_checker
                )
            except Exception as e:
                raise RuntimeError(f"Failed to load schema {schema_name}: {e}")

    def load_schema(self, schema_name: str) -> Dict[str, Any]:
        """Load a specific schema by name.

        Args:
            schema_name: Name of the schema (without .json extension)

        Returns:
            The loaded JSON schema

        Raises:
            KeyError: If schema not found
        """
        if schema_name not in self._schemas:
            # Try to load it if not already loaded
            schema_path = self.schema_dir / f"{schema_name}.json"
            if schema_path.exists():
                with open(schema_path, "r") as f:
                    schema = json.load(f)
                self._schemas[schema_name] = schema
                self._validators[schema_name] = Draft7Validator(
                    schema, format_checker=self._format_checker
                )
            else:
                raise KeyError(f"Schema '{schema_name}' not found")

        return self._schemas[schema_name]

    def validate_json(self, data: Union[Dict[str, Any], str], schema_name: str) -> Dict[str, Any]:
        """Validate JSON data against a schema.

        Args:
            data: JSON data to validate (dict or JSON string)
            schema_name: Name of the schema to validate against

        Returns:
            The validated data as a dictionary

        Raises:
            ValidationError: If validation fails
            KeyError: If schema not found
            json.JSONDecodeError: If data is invalid JSON string
        """
        # Convert JSON string to dict if needed
        if isinstance(data, str):
            parsed_data = json.loads(data)
            if not isinstance(parsed_data, dict):
                raise ValidationError(f"Expected JSON object, got {type(parsed_data).__name__}")
            data = parsed_data

        # Get validator
        if schema_name not in self._validators:
            self.load_schema(schema_name)

        validator = self._validators[schema_name]

        # Validate
        errors = list(validator.iter_errors(data))
        if errors:
            # Format error messages
            error_messages = []
            for error in errors:
                path = " -> ".join(str(p) for p in error.path)
                if path:
                    error_messages.append(f"{path}: {error.message}")
                else:
                    error_messages.append(error.message)

            raise ValidationError(
                f"Validation failed for schema '{schema_name}': " + "; ".join(error_messages)
            )

        return data

    def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Get all loaded schemas.

        Returns:
            Dictionary mapping schema names to their schemas
        """
        return self._schemas.copy()

    def get_schema_names(self) -> List[str]:
        """Get list of available schema names.

        Returns:
            List of schema names
        """
        return list(self._schemas.keys())

    def get_pydantic_model(self, schema_name: str) -> Optional[Type[BaseModel]]:
        """Get the Pydantic model class for a schema.

        Args:
            schema_name: Name of the schema

        Returns:
            Pydantic model class or None if no mapping exists
        """
        return self._model_mapping.get(schema_name)

    def validate_with_model(self, data: Union[Dict[str, Any], str], schema_name: str) -> BaseModel:
        """Validate data and return as Pydantic model instance.

        Args:
            data: JSON data to validate
            schema_name: Name of the schema

        Returns:
            Validated Pydantic model instance

        Raises:
            ValidationError: If validation fails
            KeyError: If schema not found or no model mapping
        """
        # First validate against JSON schema
        validated_data = self.validate_json(data, schema_name)

        # Get Pydantic model
        model_class = self.get_pydantic_model(schema_name)
        if not model_class:
            raise KeyError(f"No Pydantic model mapped for schema '{schema_name}'")

        # Create and return model instance
        return model_class(**validated_data)

    def to_json_schema(self, model_instance: BaseModel) -> Dict[str, Any]:
        """Convert a Pydantic model instance to JSON-schema validated dict.

        Args:
            model_instance: Pydantic model instance

        Returns:
            Dictionary that validates against the corresponding JSON schema
        """
        # Get schema name from model class
        schema_name = None
        for name, model_class in self._model_mapping.items():
            if isinstance(model_instance, model_class):
                schema_name = name
                break

        if not schema_name:
            raise ValueError(f"No schema mapping for model type {type(model_instance)}")

        # Convert to dict and validate, excluding None values
        data = model_instance.model_dump(mode="json", by_alias=True, exclude_none=True)
        return self.validate_json(data, schema_name)


# Global registry instance
_registry: Optional[SchemaRegistry] = None


def get_registry() -> SchemaRegistry:
    """Get the global schema registry instance.

    Returns:
        The global SchemaRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = SchemaRegistry()
    return _registry


# Convenience functions
def load_schema(schema_name: str) -> Dict[str, Any]:
    """Load a schema by name.

    Args:
        schema_name: Name of the schema

    Returns:
        The JSON schema
    """
    return get_registry().load_schema(schema_name)


def validate_json(data: Union[Dict[str, Any], str], schema_name: str) -> Dict[str, Any]:
    """Validate JSON data against a schema.

    Args:
        data: Data to validate
        schema_name: Schema to validate against

    Returns:
        Validated data as dictionary
    """
    return get_registry().validate_json(data, schema_name)


def get_all_schemas() -> Dict[str, Dict[str, Any]]:
    """Get all available schemas.

    Returns:
        Dictionary of all schemas
    """
    return get_registry().get_all_schemas()
