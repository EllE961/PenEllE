"""Validator for Claim schemas."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .base import BaseValidator, ValidationError, ValidationResult, ValidationSeverity


class ClaimValidator(BaseValidator):
    """Validator for PenEllE claims."""

    # Valid claim types
    CLAIM_TYPES = [
        "efficacy",
        "safety",
        "mechanism",
        "epidemiology",
        "diagnosis",
        "prognosis",
        "economic",
        "quality_of_life",
        "comparative",
        "recommendation",
    ]

    # Valid claim statuses
    CLAIM_STATUSES = [
        "supported",
        "partially_supported",
        "not_supported",
        "conflicting",
        "insufficient_evidence",
        "pending_review",
    ]

    # Valid confidence levels
    CONFIDENCE_LEVELS = ["very_high", "high", "moderate", "low", "very_low"]

    def __init__(self, strict_mode: bool = True):
        """Initialize claim validator."""
        schema_path = Path(__file__).parent.parent / "json" / "claim.json"
        super().__init__(schema_path=schema_path, strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Add custom validation rules for claims."""
        # Validate claim statement
        if "statement" in data:
            self._validate_statement(data["statement"], result)

        # Validate claim metadata
        if "metadata" in data:
            self._validate_claim_metadata(data["metadata"], result)

        # Validate supporting evidence
        if "supporting_evidence" in data:
            self._validate_supporting_evidence(data["supporting_evidence"], result)

        # Validate claim assessment
        if "assessment" in data:
            self._validate_assessment(data["assessment"], result)

        # Validate relationships
        if "relationships" in data:
            self._validate_relationships(data["relationships"], result)

        # Cross-field validations
        self._validate_claim_consistency(data, result)

    def _validate_statement(self, statement: Dict[str, Any], result: ValidationResult) -> None:
        """Validate claim statement structure."""
        # Check main text
        if "text" not in statement or not statement["text"]:
            error = ValidationError(
                path="statement.text",
                message="Claim statement text is required",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)
        elif len(statement["text"]) > 1000:
            warning = ValidationError(
                path="statement.text",
                message="Claim statement is very long (>1000 characters)",
                severity=ValidationSeverity.WARNING,
            )
            result.add_warning(warning)

        # Validate structured components if present
        if "structured" in statement:
            structured = statement["structured"]

            # Check for recommended structured fields
            recommended_fields = ["subject", "predicate", "object", "context"]
            for field in recommended_fields:
                if field not in structured:
                    warning = ValidationError(
                        path=f"statement.structured.{field}",
                        message=f"Structured claim should include '{field}'",
                        severity=ValidationSeverity.WARNING,
                    )
                    result.add_warning(warning)

            # Validate PICO elements if medical claim
            if "pico" in structured:
                self._validate_pico(structured["pico"], result)

    def _validate_pico(self, pico: Dict[str, Any], result: ValidationResult) -> None:
        """Validate PICO (Population, Intervention, Comparison, Outcome) elements."""
        pico_elements = ["population", "intervention", "comparison", "outcome"]

        # At least P and O should be present
        if "population" not in pico and "outcome" not in pico:
            error = ValidationError(
                path="statement.structured.pico",
                message="PICO must include at least Population and Outcome",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

        # Validate each PICO element
        for element in pico_elements:
            if element in pico and not pico[element]:
                warning = ValidationError(
                    path=f"statement.structured.pico.{element}",
                    message=f"PICO {element} should not be empty",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

    def _validate_claim_metadata(self, metadata: Dict[str, Any], result: ValidationResult) -> None:
        """Validate claim metadata."""
        # Check claim ID format
        if "claim_id" in metadata:
            claim_id = metadata["claim_id"]
            if not re.match(r"^CLM-[A-Z0-9]{8,}$", claim_id):
                warning = ValidationError(
                    path="metadata.claim_id",
                    message=f"Claim ID should follow format CLM-XXXXXXXX: {claim_id}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Validate claim type
        if "claim_type" in metadata:
            if metadata["claim_type"] not in self.CLAIM_TYPES:
                error = ValidationError(
                    path="metadata.claim_type",
                    message=f"Invalid claim type. Must be one of: {self.CLAIM_TYPES}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate creation timestamp
        if "created_at" in metadata:
            try:
                datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                error = ValidationError(
                    path="metadata.created_at",
                    message="created_at must be a valid ISO format timestamp",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Check source context
        if "source_context" in metadata:
            context = metadata["source_context"]
            if "section" in context and not context["section"]:
                warning = ValidationError(
                    path="metadata.source_context.section",
                    message="Source context section should not be empty",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

    def _validate_supporting_evidence(self, evidence_list: Any, result: ValidationResult) -> None:
        """Validate supporting evidence references."""
        if not isinstance(evidence_list, list):
            error = ValidationError(
                path="supporting_evidence",
                message="Supporting evidence must be a list",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)
            return

        if not evidence_list:
            warning = ValidationError(
                path="supporting_evidence",
                message="Claim has no supporting evidence",
                severity=ValidationSeverity.WARNING,
            )
            result.add_warning(warning)

        evidence_ids = set()
        for i, evidence in enumerate(evidence_list):
            path_prefix = f"supporting_evidence[{i}]"

            # Check evidence reference
            if "evidence_id" not in evidence:
                error = ValidationError(
                    path=f"{path_prefix}.evidence_id",
                    message="Evidence reference must include evidence_id",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)
            else:
                # Check for duplicate evidence
                ev_id = evidence["evidence_id"]
                if ev_id in evidence_ids:
                    warning = ValidationError(
                        path=f"{path_prefix}.evidence_id",
                        message=f"Duplicate evidence reference: {ev_id}",
                        severity=ValidationSeverity.WARNING,
                    )
                    result.add_warning(warning)
                evidence_ids.add(ev_id)

            # Validate relevance score
            if "relevance_score" in evidence:
                score = evidence["relevance_score"]
                if not isinstance(score, (int, float)) or score < 0 or score > 1:
                    error = ValidationError(
                        path=f"{path_prefix}.relevance_score",
                        message="Relevance score must be between 0 and 1",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Validate support type
            if "support_type" in evidence:
                valid_types = ["supports", "contradicts", "qualifies", "neutral"]
                if evidence["support_type"] not in valid_types:
                    error = ValidationError(
                        path=f"{path_prefix}.support_type",
                        message=f"Invalid support type. Must be one of: {valid_types}",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

    def _validate_assessment(self, assessment: Dict[str, Any], result: ValidationResult) -> None:
        """Validate claim assessment."""
        # Validate status
        if "status" in assessment:
            if assessment["status"] not in self.CLAIM_STATUSES:
                error = ValidationError(
                    path="assessment.status",
                    message=f"Invalid claim status. Must be one of: {self.CLAIM_STATUSES}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate confidence level
        if "confidence_level" in assessment:
            if assessment["confidence_level"] not in self.CONFIDENCE_LEVELS:
                error = ValidationError(
                    path="assessment.confidence_level",
                    message=f"Invalid confidence level. Must be one of: {self.CONFIDENCE_LEVELS}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate strength of evidence
        if "strength_of_evidence" in assessment:
            strength = assessment["strength_of_evidence"]
            if isinstance(strength, dict):
                # Validate individual strength components
                if "quality" in strength:
                    self._validate_strength_component(
                        strength["quality"], "assessment.strength_of_evidence.quality", result
                    )
                if "quantity" in strength:
                    self._validate_strength_component(
                        strength["quantity"], "assessment.strength_of_evidence.quantity", result
                    )
                if "consistency" in strength:
                    self._validate_strength_component(
                        strength["consistency"],
                        "assessment.strength_of_evidence.consistency",
                        result,
                    )

        # Validate limitations
        if "limitations" in assessment:
            limitations = assessment["limitations"]
            if isinstance(limitations, list):
                for i, limitation in enumerate(limitations):
                    if not limitation or not isinstance(limitation, str):
                        warning = ValidationError(
                            path=f"assessment.limitations[{i}]",
                            message="Limitation should be a non-empty string",
                            severity=ValidationSeverity.WARNING,
                        )
                        result.add_warning(warning)

    def _validate_strength_component(self, value: Any, path: str, result: ValidationResult) -> None:
        """Validate strength of evidence component."""
        valid_values = ["very_strong", "strong", "moderate", "weak", "very_weak"]
        if value not in valid_values:
            error = ValidationError(
                path=path,
                message=f"Invalid strength value. Must be one of: {valid_values}",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

    def _validate_relationships(
        self, relationships: Dict[str, Any], result: ValidationResult
    ) -> None:
        """Validate claim relationships."""
        # Validate parent claims
        if "parent_claims" in relationships:
            parent_claims = relationships["parent_claims"]
            if isinstance(parent_claims, list):
                for i, parent_id in enumerate(parent_claims):
                    if not parent_id or not isinstance(parent_id, str):
                        error = ValidationError(
                            path=f"relationships.parent_claims[{i}]",
                            message="Parent claim ID must be a non-empty string",
                            severity=ValidationSeverity.ERROR,
                        )
                        result.add_error(error)

        # Validate related claims
        if "related_claims" in relationships:
            related = relationships["related_claims"]
            if isinstance(related, list):
                for i, rel in enumerate(related):
                    if isinstance(rel, dict):
                        # Check required fields
                        if "claim_id" not in rel:
                            error = ValidationError(
                                path=f"relationships.related_claims[{i}].claim_id",
                                message="Related claim must have claim_id",
                                severity=ValidationSeverity.ERROR,
                            )
                            result.add_error(error)

                        # Validate relationship type
                        if "relationship_type" in rel:
                            valid_types = [
                                "supports",
                                "contradicts",
                                "qualifies",
                                "extends",
                                "depends_on",
                            ]
                            if rel["relationship_type"] not in valid_types:
                                warning = ValidationError(
                                    path=f"relationships.related_claims[{i}].relationship_type",
                                    message=f"Unknown relationship type: {rel['relationship_type']}",
                                    severity=ValidationSeverity.WARNING,
                                )
                                result.add_warning(warning)

    def _validate_claim_consistency(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate consistency between claim fields."""
        # Check that assessment matches evidence
        if "assessment" in data and "supporting_evidence" in data:
            status = data["assessment"].get("status")
            evidence = data["supporting_evidence"]

            # If claim is supported, should have supporting evidence
            if status == "supported" and not evidence:
                warning = ValidationError(
                    path="supporting_evidence",
                    message="Supported claim should have supporting evidence",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

            # If insufficient evidence, should note this
            if status == "insufficient_evidence" and len(evidence) > 5:
                warning = ValidationError(
                    path="assessment.status",
                    message="Status is 'insufficient_evidence' but multiple evidence items provided",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Check confidence level consistency
        if "assessment" in data:
            assessment = data["assessment"]
            confidence = assessment.get("confidence_level")
            strength = assessment.get("strength_of_evidence", {})

            # Very high confidence should have strong evidence
            if confidence == "very_high":
                quality = strength.get("quality")
                if quality and quality in ["weak", "very_weak"]:
                    warning = ValidationError(
                        path="assessment",
                        message="Very high confidence inconsistent with weak evidence quality",
                        severity=ValidationSeverity.WARNING,
                    )
                    result.add_warning(warning)
