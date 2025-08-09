"""Comprehensive tests for ClaimValidator."""

from datetime import datetime
from uuid import uuid4

import pytest

from src.core.schemas.validators.claim_validator import ClaimValidator


class TestClaimValidatorComprehensive:
    """Comprehensive test cases for ClaimValidator."""

    @pytest.fixture()
    def validator(self):
        """Create a ClaimValidator instance."""
        return ClaimValidator(strict_mode=True)

    @pytest.fixture()
    def base_claim(self):
        """Create a base valid claim structure."""
        return {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "claim_text": "Drug X reduces symptoms by 50% in patients with condition Y",
            "claim_type": "causal",
            "supporting_evidence_ids": [str(uuid4()), str(uuid4())],
            "confidence_score": 0.87,
            "verification_status": "verified",
            "section_id": str(uuid4()),
            "position": {"paragraph": 3, "sentence": 2},
            "metadata": {"nli_score": 0.92, "contradicting_evidence_ids": []},
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    def test_valid_claim(self, validator, base_claim):
        """Test validation of a completely valid claim."""
        result = validator.validate(base_claim)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_claim_text_validation(self, validator, base_claim):
        """Test claim_text validation rules."""
        # Test missing claim text
        claim = base_claim.copy()
        del claim["claim_text"]
        result = validator.validate(claim)
        assert not result.is_valid

        # Test very long claim text
        claim = base_claim.copy()
        claim["claim_text"] = "x" * 1001
        result = validator.validate(claim)
        # According to the schema, any string is valid (even empty)
        assert result.is_valid

        # Test empty claim text is valid per schema
        claim = base_claim.copy()
        claim["claim_text"] = ""
        result = validator.validate(claim)
        # Empty string is technically valid per JSON schema
        assert result.is_valid

    def test_metadata_validation(self, validator, base_claim):
        """Test metadata validation."""
        # Test invalid NLI score
        claim = base_claim.copy()
        claim["metadata"]["nli_score"] = 1.5
        result = validator.validate(claim)
        assert not result.is_valid
        # Check for nli_score in either message or path
        assert any(
            "nli_score" in str(error.message) or "nli_score" in str(error.path)
            for error in result.errors
        )

        # Test valid NLI score boundaries
        claim = base_claim.copy()
        claim["metadata"]["nli_score"] = 0.0
        result = validator.validate(claim)
        assert result.is_valid

        claim["metadata"]["nli_score"] = 1.0
        result = validator.validate(claim)
        assert result.is_valid

    def test_supporting_evidence_validation(self, validator, base_claim):
        """Test supporting evidence validation."""
        # Test non-list evidence
        claim = base_claim.copy()
        claim["supporting_evidence_ids"] = "not a list"
        result = validator.validate(claim)
        assert not result.is_valid

        # Test empty evidence list
        claim = base_claim.copy()
        claim["supporting_evidence_ids"] = []
        result = validator.validate(claim)
        # Empty list is valid according to schema
        assert result.is_valid

        # Test invalid UUID format
        claim = base_claim.copy()
        claim["supporting_evidence_ids"] = ["not-a-uuid"]
        result = validator.validate(claim)
        assert not result.is_valid

    def test_claim_type_validation(self, validator, base_claim):
        """Test claim type validation."""
        # Test invalid claim type
        claim = base_claim.copy()
        claim["claim_type"] = "invalid_type"
        result = validator.validate(claim)
        assert not result.is_valid

        # Test valid claim types
        valid_types = ["factual", "interpretive", "evaluative", "causal", "predictive"]
        for claim_type in valid_types:
            claim = base_claim.copy()
            claim["claim_type"] = claim_type
            result = validator.validate(claim)
            assert result.is_valid

    def test_verification_status_validation(self, validator, base_claim):
        """Test verification status validation."""
        # Test invalid status
        claim = base_claim.copy()
        claim["verification_status"] = "invalid_status"
        result = validator.validate(claim)
        assert not result.is_valid

        # Test valid statuses
        valid_statuses = ["verified", "unverified", "disputed", "retracted"]
        for status in valid_statuses:
            claim = base_claim.copy()
            claim["verification_status"] = status
            result = validator.validate(claim)
            assert result.is_valid

    def test_confidence_score_validation(self, validator, base_claim):
        """Test confidence score validation."""
        # Test too high
        claim = base_claim.copy()
        claim["confidence_score"] = 1.5
        result = validator.validate(claim)
        assert not result.is_valid

        # Test negative
        claim = base_claim.copy()
        claim["confidence_score"] = -0.1
        result = validator.validate(claim)
        assert not result.is_valid

        # Test valid boundaries
        claim = base_claim.copy()
        claim["confidence_score"] = 0.0
        result = validator.validate(claim)
        assert result.is_valid

        claim["confidence_score"] = 1.0
        result = validator.validate(claim)
        assert result.is_valid

    def test_position_validation(self, validator, base_claim):
        """Test position object validation."""
        # Test negative values
        claim = base_claim.copy()
        claim["position"]["paragraph"] = -1
        result = validator.validate(claim)
        assert not result.is_valid

        # Test valid position
        claim = base_claim.copy()
        claim["position"] = {"paragraph": 0, "sentence": 0}
        result = validator.validate(claim)
        assert result.is_valid

    def test_datetime_validation(self, validator, base_claim):
        """Test datetime field validation."""
        # Test invalid datetime format
        claim = base_claim.copy()
        claim["created_at"] = "not-a-datetime"
        result = validator.validate(claim)
        assert not result.is_valid

        # Test valid ISO format
        claim = base_claim.copy()
        claim["created_at"] = "2023-01-01T00:00:00Z"
        result = validator.validate(claim)
        assert result.is_valid

    def test_required_fields(self, validator, base_claim):
        """Test required fields validation."""
        required_fields = [
            "schema_version",
            "id",
            "run_id",
            "claim_text",
            "claim_type",
            "supporting_evidence_ids",
        ]

        for field in required_fields:
            claim = base_claim.copy()
            del claim[field]
            result = validator.validate(claim)
            assert not result.is_valid
            assert any(field in str(error.message) for error in result.errors)

    def test_additional_properties(self, validator, base_claim):
        """Test that additional properties are not allowed."""
        claim = base_claim.copy()
        claim["extra_field"] = "should not be allowed"
        result = validator.validate(claim)
        assert not result.is_valid
        assert any("additional" in str(error.message).lower() for error in result.errors)

    def test_non_strict_mode(self):
        """Test validation in non-strict mode."""
        validator = ClaimValidator(strict_mode=False)

        # Create claim with missing required fields
        claim = {
            "claim_text": "Test claim",
            "claim_type": "causal",
        }

        result = validator.validate(claim)
        # Should still fail for missing required fields
        assert not result.is_valid

    def test_edge_cases(self, validator, base_claim):
        """Test edge cases and boundary conditions."""
        # Test UUID validation
        claim = base_claim.copy()
        claim["id"] = "invalid-uuid"
        result = validator.validate(claim)
        assert not result.is_valid

        # Test empty string in array fields
        claim = base_claim.copy()
        claim["supporting_evidence_ids"] = [""]
        result = validator.validate(claim)
        assert not result.is_valid  # Empty string is not a valid UUID
