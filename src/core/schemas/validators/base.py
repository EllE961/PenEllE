"""Base validator class for JSON schema validation in PenEllE."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema
from jsonschema import Draft7Validator


class ValidationSeverity(Enum):
    """Severity levels for validation errors."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationError:
    """Represents a validation error with context."""

    path: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    schema_path: Optional[str] = None
    instance: Optional[Any] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "message": self.message,
            "severity": self.severity.value,
            "schema_path": self.schema_path,
            "instance": str(self.instance) if self.instance is not None else None,
            "context": self.context,
        }


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    validated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "metadata": self.metadata,
            "validated_at": self.validated_at.isoformat(),
        }

    def add_error(self, error: ValidationError) -> None:
        """Add an error to the result."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: ValidationError) -> None:
        """Add a warning to the result."""
        warning.severity = ValidationSeverity.WARNING
        self.warnings.append(warning)


class BaseValidator:
    """Base class for JSON schema validators in PenEllE."""

    def __init__(
        self,
        schema_path: Optional[Path] = None,
        schema_dict: Optional[Dict[str, Any]] = None,
        strict_mode: bool = True,
    ):
        """
        Initialize validator with either a schema file path or schema dict.

        Args:
            schema_path: Path to JSON schema file
            schema_dict: Schema as dictionary
            strict_mode: If True, treat warnings as errors
        """
        self.strict_mode = strict_mode
        self._errors: List[ValidationError] = []
        self._warnings: List[ValidationError] = []
        self.schema_path: Optional[Path] = None

        if schema_path:
            self.schema = self._load_schema(schema_path)
            self.schema_path = schema_path
        elif schema_dict:
            self.schema = schema_dict
            self.schema_path = None
        else:
            raise ValueError("Either schema_path or schema_dict must be provided")

        # Create validator with custom format checkers
        self.validator = self._create_validator(self.schema)

    def _load_schema(self, schema_path: Path) -> Dict[str, Any]:
        """Load JSON schema from file."""
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, "r") as f:
            data = json.load(f)
            return data  # type: ignore[no-any-return]

    def _create_validator(self, schema: Dict[str, Any]) -> Draft7Validator:
        """Create a JSON schema validator with custom format checkers."""
        # Add custom format checkers if needed
        format_checker = jsonschema.FormatChecker()

        # Add date-time format checker (for JSON Schema date-time format)
        @format_checker.checks("date-time", raises=ValueError)
        def check_date_time(instance: Any) -> bool:
            if not isinstance(instance, str):
                return False
            try:
                # Try to parse as ISO 8601 datetime
                datetime.fromisoformat(instance.replace("Z", "+00:00"))
                return True
            except Exception:
                return False

        # Add custom formats for PenEllE
        @format_checker.checks("iso-date", raises=ValueError)
        def check_iso_date(instance: Any) -> bool:
            if not isinstance(instance, str):
                return False
            try:
                datetime.fromisoformat(instance.replace("Z", "+00:00"))
                return True
            except Exception:
                return False

        return Draft7Validator(schema, format_checker=format_checker)

    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """
        Validate data against schema.

        Args:
            data: Data to validate

        Returns:
            ValidationResult with errors and warnings
        """
        self._errors = []
        self._warnings = []
        result = ValidationResult(is_valid=True)

        # Basic JSON schema validation
        try:
            self.validator.validate(data)
        except jsonschema.ValidationError as e:
            self._add_validation_error(e, result)
        except jsonschema.SchemaError as e:
            error = ValidationError(
                path="$", message=f"Schema error: {str(e)}", severity=ValidationSeverity.ERROR
            )
            result.add_error(error)

        # Run custom validations (to be implemented by subclasses)
        self._custom_validate(data, result)

        # Apply strict mode
        if self.strict_mode and result.warnings:
            for warning in result.warnings:
                warning.severity = ValidationSeverity.ERROR
                result.errors.append(warning)
            result.warnings = []
            result.is_valid = False

        return result

    def _add_validation_error(
        self, error: jsonschema.ValidationError, result: ValidationResult
    ) -> None:
        """Convert jsonschema error to our ValidationError format."""
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "$"

        validation_error = ValidationError(
            path=path,
            message=error.message,
            severity=ValidationSeverity.ERROR,
            schema_path=(
                ".".join(str(p) for p in error.absolute_schema_path)
                if error.absolute_schema_path
                else None
            ),
            instance=error.instance,
            context={"validator": error.validator, "validator_value": error.validator_value},
        )

        result.add_error(validation_error)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """
        Override in subclasses to add custom validation logic.

        Args:
            data: Data being validated
            result: ValidationResult to add errors/warnings to
        """
        pass

    def validate_batch(self, data_list: List[Dict[str, Any]]) -> List[ValidationResult]:
        """
        Validate multiple data items.

        Args:
            data_list: List of data items to validate

        Returns:
            List of ValidationResult objects
        """
        return [self.validate(data) for data in data_list]

    def get_errors(self) -> List[ValidationError]:
        """Get list of validation errors from last validation."""
        return self._errors.copy()

    def get_warnings(self) -> List[ValidationError]:
        """Get list of validation warnings from last validation."""
        return self._warnings.copy()

    def validate_required_fields(
        self, data: Dict[str, Any], required_fields: List[str], result: ValidationResult
    ) -> None:
        """Helper to validate required fields exist and are non-empty."""
        for required_field in required_fields:
            if required_field not in data:
                error = ValidationError(
                    path=required_field,
                    message=f"Required field '{required_field}' is missing",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)
            elif not data[required_field]:
                warning = ValidationError(
                    path=required_field,
                    message=f"Required field '{required_field}' is empty",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

    def validate_enum_field(
        self, data: Dict[str, Any], field: str, allowed_values: List[str], result: ValidationResult
    ) -> None:
        """Helper to validate enum fields."""
        if field in data and data[field] not in allowed_values:
            error = ValidationError(
                path=field,
                message=f"Invalid value '{data[field]}' for field '{field}'. Allowed values: {allowed_values}",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)
