"""Simple tests for ClaimValidator that match the actual schema."""

from datetime import datetime
from uuid import uuid4

import pytest

from src.core.schemas.validators.claim_validator import ClaimValidator


class TestClaimValidatorSimple:
    """Simple test cases for ClaimValidator based on actual schema."""

    @pytest.fixture()
    def validator(self):
        """Create a ClaimValidator instance."""
        return ClaimValidator(strict_mode=True)

    @pytest.fixture()
    def valid_claim(self):
        """Create a valid claim matching the schema."""
        return {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "claim_text": "Drug X reduces symptoms by 50%",
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

    def test_valid_claim_passes(self, validator, valid_claim):
        """Test that a valid claim passes validation."""
        result = validator.validate(valid_claim)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_claim_type(self, validator, valid_claim):
        """Test validation fails for invalid claim type."""
        valid_claim["claim_type"] = "invalid_type"
        result = validator.validate(valid_claim)
        assert not result.is_valid
        assert any("claim_type" in str(e.path) for e in result.errors)

    def test_confidence_score_bounds(self, validator, valid_claim):
        """Test confidence score validation."""
        # Test too high
        valid_claim["confidence_score"] = 1.5
        result = validator.validate(valid_claim)
        assert not result.is_valid

        # Test negative
        valid_claim["confidence_score"] = -0.1
        result = validator.validate(valid_claim)
        assert not result.is_valid

        # Test valid boundaries
        valid_claim["confidence_score"] = 0.0
        result = validator.validate(valid_claim)
        assert result.is_valid

        valid_claim["confidence_score"] = 1.0
        result = validator.validate(valid_claim)
        assert result.is_valid

    def test_missing_required_fields(self, validator, valid_claim):
        """Test validation fails when required fields are missing."""
        required_fields = [
            "schema_version",
            "id",
            "run_id",
            "claim_text",
            "claim_type",
            "supporting_evidence_ids",
        ]

        for field in required_fields:
            claim = valid_claim.copy()
            del claim[field]
            result = validator.validate(claim)
            assert not result.is_valid
            assert any(field in str(e.message) for e in result.errors)

    def test_valid_claim_types(self, validator, valid_claim):
        """Test all valid claim types."""
        valid_types = ["factual", "interpretive", "evaluative", "causal", "predictive"]

        for claim_type in valid_types:
            valid_claim["claim_type"] = claim_type
            result = validator.validate(valid_claim)
            assert result.is_valid

    def test_valid_verification_statuses(self, validator, valid_claim):
        """Test all valid verification statuses."""
        valid_statuses = ["verified", "unverified", "disputed", "retracted"]

        for status in valid_statuses:
            valid_claim["verification_status"] = status
            result = validator.validate(valid_claim)
            assert result.is_valid

    def test_invalid_verification_status(self, validator, valid_claim):
        """Test invalid verification status."""
        valid_claim["verification_status"] = "fake"
        result = validator.validate(valid_claim)
        assert not result.is_valid

    def test_empty_supporting_evidence(self, validator, valid_claim):
        """Test empty supporting evidence list."""
        valid_claim["supporting_evidence_ids"] = []
        result = validator.validate(valid_claim)
        # Empty list should be valid according to schema
        assert result.is_valid

    def test_invalid_uuid_format(self, validator, valid_claim):
        """Test invalid UUID formats."""
        valid_claim["id"] = "not-a-uuid"
        result = validator.validate(valid_claim)
        assert not result.is_valid

    def test_invalid_datetime_format(self, validator, valid_claim):
        """Test invalid datetime format."""
        valid_claim["created_at"] = "not-a-datetime"
        result = validator.validate(valid_claim)
        assert not result.is_valid

    def test_position_validation(self, validator, valid_claim):
        """Test position object validation."""
        # Test negative values
        valid_claim["position"]["paragraph"] = -1
        result = validator.validate(valid_claim)
        assert not result.is_valid

        # Test valid position
        valid_claim["position"] = {"paragraph": 0, "sentence": 0}
        result = validator.validate(valid_claim)
        assert result.is_valid

    def test_metadata_nli_score_bounds(self, validator, valid_claim):
        """Test NLI score validation in metadata."""
        # Test too high
        valid_claim["metadata"]["nli_score"] = 1.5
        result = validator.validate(valid_claim)
        assert not result.is_valid

        # Test valid boundaries
        valid_claim["metadata"]["nli_score"] = 0.0
        result = validator.validate(valid_claim)
        assert result.is_valid

        valid_claim["metadata"]["nli_score"] = 1.0
        result = validator.validate(valid_claim)
        assert result.is_valid

    def test_additional_properties_not_allowed(self, validator, valid_claim):
        """Test that additional properties are not allowed."""
        valid_claim["extra_field"] = "should not be allowed"
        result = validator.validate(valid_claim)
        assert not result.is_valid
        assert any("additional" in str(e.message).lower() for e in result.errors)

    def test_custom_validation_with_basic_claim(self, validator, valid_claim):
        """Test that custom validation doesn't break basic claims."""
        # The validator has custom validation for advanced fields not in the schema
        # This should not affect basic validation
        result = validator.validate(valid_claim)
        assert result.is_valid

    def test_non_strict_mode(self):
        """Test validation in non-strict mode."""
        validator = ClaimValidator(strict_mode=False)

        # Create claim missing some required fields
        claim = {"claim_text": "Test claim", "claim_type": "causal"}

        result = validator.validate(claim)
        # Should still fail for missing required fields even in non-strict mode
        assert not result.is_valid
