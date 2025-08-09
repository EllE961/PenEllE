"""Simple tests to increase coverage."""

from datetime import datetime

from src.core.schemas.validators.base import ValidationError, ValidationResult, ValidationSeverity


class TestValidationModels:
    """Test validation models."""

    def test_validation_error_creation(self):
        """Test ValidationError creation."""
        error = ValidationError(
            path="test.path",
            message="Test error message",
            severity=ValidationSeverity.ERROR,
        )
        assert error.path == "test.path"
        assert error.message == "Test error message"
        assert error.severity == ValidationSeverity.ERROR

    def test_validation_error_with_context(self):
        """Test ValidationError with context."""
        error = ValidationError(
            path="field",
            message="Error message",
            severity=ValidationSeverity.WARNING,
            context={"key": "value"},
        )
        assert error.context == {"key": "value"}

    def test_validation_result_creation(self):
        """Test ValidationResult creation."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
            metadata={"test": "data"},
        )
        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metadata["test"] == "data"

    def test_validation_severity_enum(self):
        """Test ValidationSeverity enum values."""
        assert ValidationSeverity.ERROR.value == "error"
        assert ValidationSeverity.WARNING.value == "warning"
        assert ValidationSeverity.INFO.value == "info"

    def test_validation_error_to_dict(self):
        """Test converting ValidationError to dict."""
        error = ValidationError(
            path="test.field",
            message="Test error",
            severity=ValidationSeverity.ERROR,
            schema_path="properties.test.field",
            instance="bad_value",
        )

        error_dict = error.to_dict()
        assert error_dict["path"] == "test.field"
        assert error_dict["message"] == "Test error"
        assert error_dict["severity"] == "error"
        assert error_dict["schema_path"] == "properties.test.field"
        assert error_dict["instance"] == "bad_value"

    def test_validation_result_to_dict(self):
        """Test converting ValidationResult to dict."""
        error = ValidationError(
            path="field1", message="Error message", severity=ValidationSeverity.ERROR
        )
        warning = ValidationError(
            path="field2", message="Warning message", severity=ValidationSeverity.WARNING
        )

        result = ValidationResult(
            is_valid=False, errors=[error], warnings=[warning], metadata={"test": "value"}
        )

        result_dict = result.to_dict()
        assert result_dict["is_valid"] is False
        assert len(result_dict["errors"]) == 1
        assert len(result_dict["warnings"]) == 1
        assert result_dict["metadata"]["test"] == "value"
        assert "validated_at" in result_dict

        # Check that validated_at is properly formatted
        validated_at = datetime.fromisoformat(result_dict["validated_at"].replace("Z", "+00:00"))
        assert isinstance(validated_at, datetime)
