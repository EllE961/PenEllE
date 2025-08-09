"""Validator for all output schemas (draft sections, quality reports, manifests)."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseValidator, ValidationError, ValidationResult, ValidationSeverity


class OutputValidator(BaseValidator):
    """Base validator for PenEllE output schemas."""

    OUTPUT_TYPES = [
        "draft_section",
        "quality_report",
        "run_manifest",
        "search_result",
        "structured_input",
    ]

    def __init__(self, output_type: str, strict_mode: bool = True):
        """
        Initialize output validator.

        Args:
            output_type: Type of output to validate
            strict_mode: If True, treat warnings as errors
        """
        if output_type not in self.OUTPUT_TYPES:
            raise ValueError(f"Invalid output type. Must be one of: {self.OUTPUT_TYPES}")

        self.output_type = output_type
        schema_file = f"{output_type}.json"
        schema_path = Path(__file__).parent.parent / "json" / schema_file

        super().__init__(schema_path=schema_path, strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Route to specific validation based on output type."""
        # Base implementation does nothing - subclasses override this
        pass


class DraftSectionValidator(OutputValidator):
    """Validator for draft section outputs."""

    SECTION_TYPES = [
        "introduction",
        "background",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "abstract",
        "summary",
        "literature_review",
        "recommendations",
        "limitations",
    ]

    def __init__(self, strict_mode: bool = True):
        """Initialize draft section validator."""
        super().__init__(output_type="draft_section", strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate draft section specific fields."""
        self._validate_draft_section(data, result)

    def _validate_draft_section(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate draft section specific fields."""
        # According to draft_section.json, content is just a string
        if "content" in data and not isinstance(data["content"], str):
            error = ValidationError(
                path="content",
                message="Content must be a string",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

        # Validate section_type enum
        if "section_type" in data:
            valid_types = [
                "introduction",
                "methodology",
                "results",
                "discussion",
                "conclusion",
                "abstract",
                "custom",
            ]
            if data["section_type"] not in valid_types:
                error = ValidationError(
                    path="section_type",
                    message=f"Invalid section type. Must be one of: {valid_types}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_section_metadata(
        self, metadata: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate section metadata."""
        # Check section type
        if "section_type" in metadata:
            if metadata["section_type"] not in self.SECTION_TYPES:
                warning = ValidationError(
                    path="metadata.section_type",
                    message=f"Unknown section type: {metadata['section_type']}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Validate version
        if "version" in metadata:
            version = metadata["version"]
            if not re.match(r"^\d+\.\d+(\.\d+)?$", str(version)):
                warning = ValidationError(
                    path="metadata.version",
                    message=f"Version should follow semantic versioning: {version}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Check word count
        if "word_count" in metadata:
            word_count = metadata["word_count"]
            if not isinstance(word_count, int) or word_count < 0:
                error = ValidationError(
                    path="metadata.word_count",
                    message="Word count must be a non-negative integer",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_section_content(self, content: Dict[str, Any], result: ValidationResult) -> None:
        """Validate section content structure."""
        # Check main text
        if "text" not in content or not content["text"]:
            error = ValidationError(
                path="content.text",
                message="Section content text is required",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

        # Validate formatting
        if "formatting" in content:
            formatting = content["formatting"]
            if "style" in formatting:
                valid_styles = ["plain", "markdown", "html", "latex"]
                if formatting["style"] not in valid_styles:
                    error = ValidationError(
                        path="content.formatting.style",
                        message=f"Invalid formatting style. Must be one of: {valid_styles}",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

        # Check subsections
        if "subsections" in content:
            subsections = content["subsections"]
            if isinstance(subsections, list):
                for i, subsection in enumerate(subsections):
                    self._validate_subsection(subsection, f"content.subsections[{i}]", result)

    def _validate_subsection(
        self, subsection: Dict[str, Any], path: str, result: ValidationResult
    ) -> None:
        """Validate individual subsection."""
        # Check required fields
        if "title" not in subsection:
            error = ValidationError(
                path=f"{path}.title",
                message="Subsection must have a title",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

        if "content" not in subsection:
            error = ValidationError(
                path=f"{path}.content",
                message="Subsection must have content",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

    def _validate_citations(
        self, citations: List[Dict[str, Any]], result: ValidationResult
    ) -> None:
        """Validate citation references."""
        citation_keys = set()

        for i, citation in enumerate(citations):
            path_prefix = f"citations[{i}]"

            # Check citation key
            if "key" not in citation:
                error = ValidationError(
                    path=f"{path_prefix}.key",
                    message="Citation must have a key",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)
            else:
                key = citation["key"]
                if key in citation_keys:
                    error = ValidationError(
                        path=f"{path_prefix}.key",
                        message=f"Duplicate citation key: {key}",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)
                citation_keys.add(key)

            # Check source reference
            if "source_id" not in citation:
                error = ValidationError(
                    path=f"{path_prefix}.source_id",
                    message="Citation must reference a source_id",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_revision_history(
        self, history: List[Dict[str, Any]], result: ValidationResult
    ) -> None:
        """Validate revision history entries."""
        timestamps = []

        for i, revision in enumerate(history):
            path_prefix = f"revision_history[{i}]"

            # Check timestamp
            if "timestamp" in revision:
                try:
                    ts = datetime.fromisoformat(revision["timestamp"].replace("Z", "+00:00"))
                    timestamps.append(ts)
                except (ValueError, AttributeError):
                    error = ValidationError(
                        path=f"{path_prefix}.timestamp",
                        message="Invalid timestamp format",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Check change description
            if "changes" not in revision or not revision["changes"]:
                warning = ValidationError(
                    path=f"{path_prefix}.changes",
                    message="Revision should describe changes made",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Check chronological order
        if len(timestamps) > 1:
            for i in range(1, len(timestamps)):
                if timestamps[i] < timestamps[i - 1]:
                    error = ValidationError(
                        path="revision_history",
                        message="Revision history must be in chronological order",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)
                    break


class QualityReportValidator(OutputValidator):
    """Validator for quality report outputs."""

    QUALITY_DIMENSIONS = [
        "accuracy",
        "completeness",
        "clarity",
        "coherence",
        "relevance",
        "evidence_quality",
        "citation_accuracy",
    ]

    def __init__(self, strict_mode: bool = True):
        """Initialize quality report validator."""
        super().__init__(output_type="quality_report", strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate quality report specific fields."""
        self._validate_quality_report(data, result)

    def _validate_quality_report(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate quality report specific fields."""
        # According to quality_report.json, the structure is different
        # It has overall_score, passed, metrics, issues, recommendations

        # Validate overall_score range
        if "overall_score" in data:
            score = data["overall_score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                error = ValidationError(
                    path="overall_score",
                    message="Overall score must be between 0 and 1",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate metrics structure
        if "metrics" in data and isinstance(data["metrics"], dict):
            # Basic validation - just check it's a dict with expected keys
            pass

        # Issues are an array in the schema
        if "issues" in data and not isinstance(data["issues"], list):
            error = ValidationError(
                path="issues",
                message="Issues must be an array",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

    def _validate_overall_assessment(
        self, assessment: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate overall quality assessment."""
        # Check quality score
        if "score" in assessment:
            score = assessment["score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 100:
                error = ValidationError(
                    path="overall_assessment.score",
                    message="Quality score must be between 0 and 100",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Check grade
        if "grade" in assessment:
            valid_grades = ["A", "B", "C", "D", "F"]
            if assessment["grade"] not in valid_grades:
                error = ValidationError(
                    path="overall_assessment.grade",
                    message=f"Invalid grade. Must be one of: {valid_grades}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_dimension_scores(
        self, dimensions: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate individual dimension scores."""
        for dimension, score_data in dimensions.items():
            path_prefix = f"dimension_scores.{dimension}"

            if dimension not in self.QUALITY_DIMENSIONS:
                warning = ValidationError(
                    path=path_prefix,
                    message=f"Unknown quality dimension: {dimension}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

            if isinstance(score_data, dict):
                # Validate score
                if "score" in score_data:
                    score = score_data["score"]
                    if not isinstance(score, (int, float)) or score < 0 or score > 10:
                        error = ValidationError(
                            path=f"{path_prefix}.score",
                            message="Dimension score must be between 0 and 10",
                            severity=ValidationSeverity.ERROR,
                        )
                        result.add_error(error)

    def _validate_quality_issues(
        self, issues: List[Dict[str, Any]], result: ValidationResult
    ) -> None:
        """Validate quality issues found."""
        for i, issue in enumerate(issues):
            path_prefix = f"issues[{i}]"

            # Check severity
            if "severity" in issue:
                valid_severities = ["critical", "major", "minor", "trivial"]
                if issue["severity"] not in valid_severities:
                    error = ValidationError(
                        path=f"{path_prefix}.severity",
                        message=f"Invalid severity. Must be one of: {valid_severities}",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Check location
            if "location" not in issue:
                warning = ValidationError(
                    path=f"{path_prefix}.location",
                    message="Issue should specify location",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

    def _validate_recommendations(self, recommendations: Any, result: ValidationResult) -> None:
        """Validate improvement recommendations."""
        if not isinstance(recommendations, list):
            error = ValidationError(
                path="recommendations",
                message="Recommendations must be a list",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)
            return

        for i, rec in enumerate(recommendations):
            if not rec or not isinstance(rec, str):
                warning = ValidationError(
                    path=f"recommendations[{i}]",
                    message="Recommendation should be a non-empty string",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)


class RunManifestValidator(OutputValidator):
    """Validator for run manifest outputs."""

    def __init__(self, strict_mode: bool = True):
        """Initialize run manifest validator."""
        super().__init__(output_type="run_manifest", strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate run manifest specific fields."""
        self._validate_run_manifest(data, result)

    def _validate_run_manifest(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate run manifest specific fields."""
        # Validate run summary
        if "run_summary" in data:
            self._validate_run_summary(data["run_summary"], result)

        # Validate outputs produced
        if "outputs" in data:
            self._validate_manifest_outputs(data["outputs"], result)

        # Validate performance metrics
        if "performance_metrics" in data:
            self._validate_performance_metrics(data["performance_metrics"], result)

        # Validate resource usage
        if "resource_usage" in data:
            self._validate_resource_usage(data["resource_usage"], result)

    def _validate_run_summary(self, summary: Dict[str, Any], result: ValidationResult) -> None:
        """Validate run summary information."""
        # Check status
        if "status" in summary:
            valid_statuses = ["completed", "failed", "partial", "cancelled"]
            if summary["status"] not in valid_statuses:
                error = ValidationError(
                    path="run_summary.status",
                    message=f"Invalid run status. Must be one of: {valid_statuses}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Check duration
        if "duration_seconds" in summary:
            duration = summary["duration_seconds"]
            if not isinstance(duration, (int, float)) or duration < 0:
                error = ValidationError(
                    path="run_summary.duration_seconds",
                    message="Duration must be a non-negative number",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_manifest_outputs(
        self, outputs: List[Dict[str, Any]], result: ValidationResult
    ) -> None:
        """Validate output file references."""
        for i, output in enumerate(outputs):
            path_prefix = f"outputs[{i}]"

            # Check required fields
            required_fields = ["type", "path", "size_bytes"]
            for field in required_fields:
                if field not in output:
                    error = ValidationError(
                        path=f"{path_prefix}.{field}",
                        message=f"Output must have '{field}'",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Validate file size
            if "size_bytes" in output:
                size = output["size_bytes"]
                if not isinstance(size, int) or size < 0:
                    error = ValidationError(
                        path=f"{path_prefix}.size_bytes",
                        message="File size must be a non-negative integer",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

    def _validate_performance_metrics(
        self, metrics: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate performance metrics."""
        # Validate token usage
        if "tokens_used" in metrics:
            tokens = metrics["tokens_used"]
            if isinstance(tokens, dict):
                for token_type in ["input", "output", "total"]:
                    if token_type in tokens:
                        count = tokens[token_type]
                        if not isinstance(count, int) or count < 0:
                            error = ValidationError(
                                path=f"performance_metrics.tokens_used.{token_type}",
                                message="Token count must be a non-negative integer",
                                severity=ValidationSeverity.ERROR,
                            )
                            result.add_error(error)

    def _validate_resource_usage(self, resources: Dict[str, Any], result: ValidationResult) -> None:
        """Validate resource usage information."""
        # Validate memory usage
        if "memory_mb" in resources:
            memory = resources["memory_mb"]
            if not isinstance(memory, (int, float)) or memory < 0:
                error = ValidationError(
                    path="resource_usage.memory_mb",
                    message="Memory usage must be a non-negative number",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate CPU usage
        if "cpu_percent" in resources:
            cpu = resources["cpu_percent"]
            if not isinstance(cpu, (int, float)) or cpu < 0 or cpu > 100:
                error = ValidationError(
                    path="resource_usage.cpu_percent",
                    message="CPU usage must be between 0 and 100",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)
