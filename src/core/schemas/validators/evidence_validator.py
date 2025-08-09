"""Validator for Evidence schemas including limited access evidence."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .base import BaseValidator, ValidationError, ValidationResult, ValidationSeverity


class EvidenceValidator(BaseValidator):
    """Validator for PenEllE evidence objects."""

    # Valid evidence types
    EVIDENCE_TYPES = [
        "clinical_trial",
        "observational_study",
        "systematic_review",
        "meta_analysis",
        "case_report",
        "expert_opinion",
        "guideline",
        "regulatory_document",
        "laboratory_study",
        "real_world_evidence",
    ]

    # Valid evidence quality levels
    QUALITY_LEVELS = ["high", "moderate", "low", "very_low"]

    # Valid study designs
    STUDY_DESIGNS = [
        "randomized_controlled_trial",
        "cohort",
        "case_control",
        "cross_sectional",
        "case_series",
        "ecological",
        "qualitative",
        "mixed_methods",
        "systematic_review",
        "meta_analysis",
    ]

    def __init__(self, evidence_type: str = "standard", strict_mode: bool = True):
        """
        Initialize evidence validator.

        Args:
            evidence_type: Either "standard" or "limited_access"
            strict_mode: If True, treat warnings as errors
        """
        self.evidence_type = evidence_type
        schema_file = (
            "evidence.json" if evidence_type == "standard" else "limited_access_evidence.json"
        )
        schema_path = Path(__file__).parent.parent / "json" / schema_file

        super().__init__(schema_path=schema_path, strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Add custom validation rules for evidence."""
        # For standard evidence, validate based on evidence.json schema
        if self.evidence_type == "standard":
            # Validate evidence_type enum
            if "evidence_type" in data:
                valid_types = ["statistic", "quote", "method", "casestudy", "table", "figure"]
                if data["evidence_type"] not in valid_types:
                    error = ValidationError(
                        path="evidence_type",
                        message=f"Invalid evidence type. Must be one of: {valid_types}",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Content is just a string, not a complex object
            if "content" in data and not isinstance(data["content"], str):
                error = ValidationError(
                    path="content",
                    message="Content must be a string",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Limited access specific validations
        elif self.evidence_type == "limited_access":
            self._validate_limited_access_fields(data, result)

    def _validate_metadata(self, metadata: Dict[str, Any], result: ValidationResult) -> None:
        """Validate evidence metadata."""
        # Check evidence ID format
        if "evidence_id" in metadata:
            evidence_id = metadata["evidence_id"]
            if not re.match(r"^EVD-[A-Z0-9]{8,}$", evidence_id):
                warning = ValidationError(
                    path="metadata.evidence_id",
                    message=f"Evidence ID should follow format EVD-XXXXXXXX: {evidence_id}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Validate evidence type
        if "evidence_type" in metadata:
            if metadata["evidence_type"] not in self.EVIDENCE_TYPES:
                error = ValidationError(
                    path="metadata.evidence_type",
                    message=f"Invalid evidence type. Must be one of: {self.EVIDENCE_TYPES}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate extraction timestamp
        if "extracted_at" in metadata:
            try:
                datetime.fromisoformat(metadata["extracted_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                error = ValidationError(
                    path="metadata.extracted_at",
                    message="extracted_at must be a valid ISO format timestamp",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Check for required metadata fields
        required_metadata = ["evidence_id", "evidence_type", "extracted_at"]
        for field in required_metadata:
            if field not in metadata:
                error = ValidationError(
                    path=f"metadata.{field}",
                    message=f"Required metadata field '{field}' is missing",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_content(self, content: Dict[str, Any], result: ValidationResult) -> None:
        """Validate evidence content structure."""
        # Check for main content
        if "text" not in content or not content["text"]:
            error = ValidationError(
                path="content.text",
                message="Evidence content text is required",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

        # Validate highlighted sections
        if "highlights" in content:
            highlights = content["highlights"]
            if not isinstance(highlights, list):
                error = ValidationError(
                    path="content.highlights",
                    message="Highlights must be a list",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)
            else:
                for i, highlight in enumerate(highlights):
                    self._validate_highlight(highlight, f"content.highlights[{i}]", result)

        # Check content length
        if "text" in content and len(content["text"]) > 50000:
            warning = ValidationError(
                path="content.text",
                message="Evidence text is very long (>50k characters)",
                severity=ValidationSeverity.WARNING,
            )
            result.add_warning(warning)

    def _validate_highlight(
        self, highlight: Dict[str, Any], path: str, result: ValidationResult
    ) -> None:
        """Validate individual highlight structure."""
        required_fields = ["text", "start_offset", "end_offset"]
        for field in required_fields:
            if field not in highlight:
                error = ValidationError(
                    path=f"{path}.{field}",
                    message=f"Highlight missing required field '{field}'",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate offset consistency
        if "start_offset" in highlight and "end_offset" in highlight:
            start = highlight["start_offset"]
            end = highlight["end_offset"]

            if not isinstance(start, int) or not isinstance(end, int):
                error = ValidationError(
                    path=path,
                    message="Highlight offsets must be integers",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)
            elif start < 0 or end < start:
                error = ValidationError(
                    path=path,
                    message="Invalid highlight offsets: start must be >= 0 and end must be >= start",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_source_reference(self, source: Dict[str, Any], result: ValidationResult) -> None:
        """Validate source reference in evidence."""
        # Check for source ID
        if "source_id" not in source:
            error = ValidationError(
                path="source.source_id",
                message="Evidence must reference a source_id",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

        # Validate page/location reference
        if "location" in source:
            location = source["location"]
            if "page" in location:
                page = location["page"]
                if not re.match(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)?$", str(page)):
                    warning = ValidationError(
                        path="source.location.page",
                        message=f"Page reference format may be invalid: {page}",
                        severity=ValidationSeverity.WARNING,
                    )
                    result.add_warning(warning)

    def _validate_quality_assessment(
        self, quality: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate quality assessment data."""
        # Validate quality level
        if "level" in quality:
            if quality["level"] not in self.QUALITY_LEVELS:
                error = ValidationError(
                    path="quality_assessment.level",
                    message=f"Invalid quality level. Must be one of: {self.QUALITY_LEVELS}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate confidence score
        if "confidence_score" in quality:
            score = quality["confidence_score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                error = ValidationError(
                    path="quality_assessment.confidence_score",
                    message="Confidence score must be between 0 and 1",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate study design
        if "study_design" in quality:
            if quality["study_design"] not in self.STUDY_DESIGNS:
                warning = ValidationError(
                    path="quality_assessment.study_design",
                    message=f"Unknown study design: {quality['study_design']}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Validate bias assessment
        if "bias_assessment" in quality:
            self._validate_bias_assessment(quality["bias_assessment"], result)

    def _validate_bias_assessment(self, bias: Dict[str, Any], result: ValidationResult) -> None:
        """Validate bias assessment structure."""
        valid_bias_types = [
            "selection_bias",
            "performance_bias",
            "detection_bias",
            "attrition_bias",
            "reporting_bias",
            "other_bias",
        ]

        for bias_type, assessment in bias.items():
            if bias_type not in valid_bias_types:
                warning = ValidationError(
                    path=f"quality_assessment.bias_assessment.{bias_type}",
                    message=f"Unknown bias type: {bias_type}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

            if isinstance(assessment, dict):
                if "risk" in assessment:
                    valid_risks = ["low", "unclear", "high"]
                    if assessment["risk"] not in valid_risks:
                        error = ValidationError(
                            path=f"quality_assessment.bias_assessment.{bias_type}.risk",
                            message=f"Invalid bias risk level. Must be one of: {valid_risks}",
                            severity=ValidationSeverity.ERROR,
                        )
                        result.add_error(error)

    def _validate_statistical_data(self, stats: Dict[str, Any], result: ValidationResult) -> None:
        """Validate statistical data in evidence."""
        # Validate sample size
        if "sample_size" in stats:
            sample_size = stats["sample_size"]
            if not isinstance(sample_size, int) or sample_size < 1:
                error = ValidationError(
                    path="statistical_data.sample_size",
                    message="Sample size must be a positive integer",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate p-values
        if "p_value" in stats:
            p_value = stats["p_value"]
            if not isinstance(p_value, (int, float)) or p_value < 0 or p_value > 1:
                error = ValidationError(
                    path="statistical_data.p_value",
                    message="P-value must be between 0 and 1",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate confidence intervals
        if "confidence_interval" in stats:
            ci = stats["confidence_interval"]
            if isinstance(ci, dict):
                if "lower" in ci and "upper" in ci:
                    if ci["lower"] > ci["upper"]:
                        error = ValidationError(
                            path="statistical_data.confidence_interval",
                            message="Confidence interval lower bound cannot be greater than upper bound",
                            severity=ValidationSeverity.ERROR,
                        )
                        result.add_error(error)
                else:
                    error = ValidationError(
                        path="statistical_data.confidence_interval",
                        message="Confidence interval must have 'lower' and 'upper' bounds",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

    def _validate_limited_access_fields(
        self, data: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate fields specific to limited access evidence."""
        # Check access restrictions
        if "access_restrictions" not in data:
            error = ValidationError(
                path="access_restrictions",
                message="Limited access evidence must specify access_restrictions",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)
        else:
            restrictions = data["access_restrictions"]

            # Validate access level
            if "level" in restrictions:
                valid_levels = ["confidential", "restricted", "internal_only", "embargoed"]
                if restrictions["level"] not in valid_levels:
                    error = ValidationError(
                        path="access_restrictions.level",
                        message=f"Invalid access level. Must be one of: {valid_levels}",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Validate expiration date if embargoed
            if restrictions.get("level") == "embargoed" and "expires_at" not in restrictions:
                error = ValidationError(
                    path="access_restrictions.expires_at",
                    message="Embargoed evidence must have an expiration date",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_evidence_consistency(
        self, data: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate consistency between different evidence fields."""
        # Check that statistical data matches evidence type
        if "statistical_data" in data and "metadata" in data:
            evidence_type = data["metadata"].get("evidence_type")
            if evidence_type in ["expert_opinion", "guideline"] and data["statistical_data"]:
                warning = ValidationError(
                    path="statistical_data",
                    message=f"Statistical data unexpected for evidence type '{evidence_type}'",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Check quality assessment completeness for clinical evidence
        if "metadata" in data and "quality_assessment" in data:
            evidence_type = data["metadata"].get("evidence_type")
            if evidence_type in ["clinical_trial", "observational_study"]:
                quality = data["quality_assessment"]
                recommended_fields = ["study_design", "bias_assessment", "confidence_score"]

                for field in recommended_fields:
                    if field not in quality:
                        warning = ValidationError(
                            path=f"quality_assessment.{field}",
                            message=f"Clinical evidence should include {field} in quality assessment",
                            severity=ValidationSeverity.WARNING,
                        )
                        result.add_warning(warning)
