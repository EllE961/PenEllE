"""Validator for RunIntake and RunConfiguration schemas."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseValidator, ValidationError, ValidationResult, ValidationSeverity


class RunValidator(BaseValidator):
    """Validator for PenEllE run configurations and intakes."""

    def __init__(self, schema_type: str = "configuration", strict_mode: bool = True):
        """
        Initialize run validator.

        Args:
            schema_type: Either "configuration" or "intake"
            strict_mode: If True, treat warnings as errors
        """
        self.schema_type = schema_type
        schema_file = (
            "run_configuration.json" if schema_type == "configuration" else "run_intake.json"
        )
        schema_path = Path(__file__).parent.parent / "json" / schema_file

        super().__init__(schema_path=schema_path, strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Add custom validation rules for run configurations."""
        # Validate run metadata
        if "run_metadata" in data:
            self._validate_run_metadata(data["run_metadata"], result)

        # Validate parameters
        if "parameters" in data:
            self._validate_parameters(data["parameters"], result)

        # Validate evidence configuration
        if "evidence_config" in data:
            self._validate_evidence_config(data["evidence_config"], result)

        # Validate output configuration
        if "output_config" in data:
            self._validate_output_config(data["output_config"], result)

        # Cross-field validations
        self._validate_cross_fields(data, result)

    def _validate_run_metadata(self, metadata: Dict[str, Any], result: ValidationResult) -> None:
        """Validate run metadata fields."""
        # Check job_id format
        if "job_id" in metadata:
            job_id = metadata["job_id"]
            if not job_id or not isinstance(job_id, str):
                error = ValidationError(
                    path="run_metadata.job_id",
                    message="job_id must be a non-empty string",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)
            elif not job_id.replace("-", "").replace("_", "").isalnum():
                warning = ValidationError(
                    path="run_metadata.job_id",
                    message="job_id should only contain alphanumeric characters, hyphens, and underscores",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Validate timestamp if present
        if "created_at" in metadata:
            try:
                datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                error = ValidationError(
                    path="run_metadata.created_at",
                    message="created_at must be a valid ISO format timestamp",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Check for recommended fields
        recommended_fields = ["user_id", "project_id", "environment"]
        for field in recommended_fields:
            if field not in metadata:
                warning = ValidationError(
                    path=f"run_metadata.{field}",
                    message=f"Recommended field '{field}' is missing from run_metadata",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

    def _validate_parameters(self, params: Dict[str, Any], result: ValidationResult) -> None:
        """Validate run parameters."""
        # Validate model parameters
        if "model_params" in params:
            model_params = params["model_params"]

            # Check temperature range
            if "temperature" in model_params:
                temp = model_params["temperature"]
                if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                    error = ValidationError(
                        path="parameters.model_params.temperature",
                        message="temperature must be a number between 0 and 2",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Check max_tokens
            if "max_tokens" in model_params:
                max_tokens = model_params["max_tokens"]
                if not isinstance(max_tokens, int) or max_tokens < 1:
                    error = ValidationError(
                        path="parameters.model_params.max_tokens",
                        message="max_tokens must be a positive integer",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)
                elif max_tokens > 100000:
                    warning = ValidationError(
                        path="parameters.model_params.max_tokens",
                        message="max_tokens is unusually high (>100k)",
                        severity=ValidationSeverity.WARNING,
                    )
                    result.add_warning(warning)

        # Validate search parameters
        if "search_params" in params:
            search_params = params["search_params"]

            if "max_results" in search_params:
                max_results = search_params["max_results"]
                if not isinstance(max_results, int) or max_results < 1:
                    error = ValidationError(
                        path="parameters.search_params.max_results",
                        message="max_results must be a positive integer",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            if "databases" in search_params:
                databases = search_params["databases"]
                if not isinstance(databases, list) or not databases:
                    error = ValidationError(
                        path="parameters.search_params.databases",
                        message="databases must be a non-empty list",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

    def _validate_evidence_config(
        self, evidence_config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate evidence configuration."""
        # Check evidence types
        if "allowed_types" in evidence_config:
            allowed_types = evidence_config["allowed_types"]
            valid_types = ["academic", "clinical", "regulatory", "internal", "external"]

            for evidence_type in allowed_types:
                if evidence_type not in valid_types:
                    error = ValidationError(
                        path="evidence_config.allowed_types",
                        message=f"Invalid evidence type '{evidence_type}'. Must be one of: {valid_types}",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

        # Check minimum confidence score
        if "min_confidence" in evidence_config:
            min_conf = evidence_config["min_confidence"]
            if not isinstance(min_conf, (int, float)) or min_conf < 0 or min_conf > 1:
                error = ValidationError(
                    path="evidence_config.min_confidence",
                    message="min_confidence must be a number between 0 and 1",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_output_config(
        self, output_config: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate output configuration."""
        # Check output formats
        if "formats" in output_config:
            formats = output_config["formats"]
            valid_formats = ["json", "markdown", "html", "pdf", "docx"]

            for fmt in formats:
                if fmt not in valid_formats:
                    warning = ValidationError(
                        path="output_config.formats",
                        message=f"Output format '{fmt}' may not be supported. Standard formats: {valid_formats}",
                        severity=ValidationSeverity.WARNING,
                    )
                    result.add_warning(warning)

        # Check output path
        if "output_path" in output_config:
            output_path = output_config["output_path"]
            if not output_path or not isinstance(output_path, str):
                error = ValidationError(
                    path="output_config.output_path",
                    message="output_path must be a non-empty string",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_cross_fields(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate relationships between different fields."""
        # Check that if search is enabled, search parameters are provided
        if data.get("enable_search", False):
            if "parameters" not in data or "search_params" not in data["parameters"]:
                error = ValidationError(
                    path="parameters.search_params",
                    message="search_params must be provided when enable_search is true",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Check output config consistency
        if "output_config" in data and "parameters" in data:
            output_formats = data["output_config"].get("formats", [])
            if "pdf" in output_formats or "docx" in output_formats:
                if not data["parameters"].get("enable_formatting", False):
                    warning = ValidationError(
                        path="parameters.enable_formatting",
                        message="enable_formatting should be true when using PDF or DOCX output formats",
                        severity=ValidationSeverity.WARNING,
                    )
                    result.add_warning(warning)


class RunIntakeValidator(RunValidator):
    """Validator specifically for RunIntake (input) schemas."""

    def __init__(self, strict_mode: bool = True):
        """Initialize RunIntake validator."""
        super().__init__(schema_type="intake", strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Add intake-specific validations."""
        super()._custom_validate(data, result)

        # Validate input sources
        if "sources" in data:
            self._validate_intake_sources(data["sources"], result)

        # Validate query/prompt
        if "query" in data:
            self._validate_query(data["query"], result)

    def _validate_intake_sources(
        self, sources: List[Dict[str, Any]], result: ValidationResult
    ) -> None:
        """Validate intake source references."""
        if not sources:
            warning = ValidationError(
                path="sources",
                message="No sources provided in intake",
                severity=ValidationSeverity.WARNING,
            )
            result.add_warning(warning)

        for i, source in enumerate(sources):
            if "id" not in source:
                error = ValidationError(
                    path=f"sources[{i}].id",
                    message=f"Source at index {i} is missing required 'id' field",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_query(self, query: Dict[str, Any], result: ValidationResult) -> None:
        """Validate query/prompt structure."""
        if "text" not in query or not query["text"]:
            error = ValidationError(
                path="query.text",
                message="Query text is required and cannot be empty",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

        # Check query length
        if "text" in query and len(query["text"]) > 10000:
            warning = ValidationError(
                path="query.text",
                message="Query text is very long (>10k characters)",
                severity=ValidationSeverity.WARNING,
            )
            result.add_warning(warning)
