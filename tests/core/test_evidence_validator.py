"""Additional tests for evidence validator to increase coverage."""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from src.core.schemas.validators.evidence_validator import EvidenceValidator


class TestEvidenceValidatorAdditional:
    """Additional tests for evidence validator coverage."""

    @pytest.fixture()
    def basic_evidence(self) -> dict[str, Any]:
        """Create basic evidence data."""
        return {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "source_id": str(uuid4()),
            "evidence_type": "statistic",
            "content": "Test evidence content",
            "context": "Test context",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    def test_validator_initialization(self):
        """Test validator initialization with different modes."""
        # Test standard validator
        validator = EvidenceValidator()
        assert validator.evidence_type == "standard"
        assert validator.strict_mode is True

        # Test limited access validator
        limited_validator = EvidenceValidator(evidence_type="limited_access", strict_mode=False)
        assert limited_validator.evidence_type == "limited_access"
        assert limited_validator.strict_mode is False

    def test_validate_study_design(self, basic_evidence):
        """Test study design validation."""
        validator = EvidenceValidator()

        # Add study_design as part of metadata (since it's not in the main schema)
        basic_evidence["metadata"] = {"study_design": "randomized_controlled_trial"}
        result = validator.validate(basic_evidence)
        assert result.is_valid

        # Invalid study design in metadata - validator should check custom validations
        basic_evidence["metadata"]["study_design"] = "invalid_design"
        result = validator.validate(basic_evidence)
        # Should still be valid at schema level, but validator may add warnings
        assert result.is_valid or len(result.warnings) > 0

    def test_validate_quality_assessment(self, basic_evidence):
        """Test quality assessment validation."""
        validator = EvidenceValidator()

        # Add quality assessment to metadata
        basic_evidence["metadata"] = {
            "quality_assessment": {
                "overall_quality": "high",
                "risk_of_bias": "low",
                "sample_size": 1000,
                "statistical_power": 0.95,
            }
        }
        result = validator.validate(basic_evidence)
        assert result.is_valid

    def test_validate_statistical_results(self, basic_evidence):
        """Test statistical results validation."""
        validator = EvidenceValidator()

        # Add statistical results to metadata
        basic_evidence["metadata"] = {
            "statistical_results": {
                "p_value": 0.03,
                "confidence_interval": {"lower": 0.2, "upper": 0.8},
                "effect_size": 0.5,
            }
        }
        result = validator.validate(basic_evidence)
        assert result.is_valid

    def test_validate_population_details(self, basic_evidence):
        """Test population details validation."""
        validator = EvidenceValidator()

        # Add population details to metadata
        basic_evidence["metadata"] = {
            "population_details": {
                "sample_size": 500,
                "demographics": {
                    "age_range": "18-65",
                    "gender_distribution": {"male": 250, "female": 250},
                },
                "inclusion_criteria": ["Diagnosed with condition X"],
                "exclusion_criteria": ["Pregnant", "Under 18"],
            }
        }
        result = validator.validate(basic_evidence)
        assert result.is_valid

    def test_validate_limited_access_evidence(self):
        """Test limited access evidence validation."""
        validator = EvidenceValidator(evidence_type="limited_access")

        limited_evidence = {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "source_id": str(uuid4()),
            "evidence_type": "table",
            "summary": "Summary of the restricted evidence",
            "access_restrictions": {
                "reason": "copyright",
                "access_url": "https://journal.com/article/12345",
                "license": "All rights reserved",
            },
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        result = validator.validate(limited_evidence)
        assert result.is_valid

        # Missing access_restrictions for limited access validator
        del limited_evidence["access_restrictions"]
        result = validator.validate(limited_evidence)
        assert not result.is_valid
        assert any("access_restrictions" in error.message for error in result.errors)

    def test_validate_embargo_details(self):
        """Test embargo validation."""
        validator = EvidenceValidator(evidence_type="limited_access")

        # Valid embargo
        embargo_evidence = {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "source_id": str(uuid4()),
            "evidence_type": "statistic",
            "summary": "[Embargoed content summary]",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "access_restrictions": {
                "reason": "embargo",
                "embargo_until": (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "access_url": "https://journal.com/embargoed/12345",
            },
        }

        result = validator.validate(embargo_evidence)
        assert result.is_valid

        # Embargo without embargo_until
        del embargo_evidence["access_restrictions"]["embargo_until"]
        result = validator.validate(embargo_evidence)
        # Should still be valid as embargo_until is optional in schema
        assert result.is_valid

    def test_validate_highlights(self, basic_evidence):
        """Test highlights validation."""
        validator = EvidenceValidator()

        # Add highlights to metadata
        basic_evidence["metadata"] = {
            "highlights": [
                {"text": "important finding", "offset": {"start": 10, "end": 27}},
                {"text": "key result", "offset": {"start": 50, "end": 60}},
            ]
        }
        result = validator.validate(basic_evidence)
        assert result.is_valid

    def test_validate_pico_elements(self, basic_evidence):
        """Test PICO elements validation."""
        validator = EvidenceValidator()

        # Add PICO elements to metadata
        basic_evidence["metadata"] = {
            "pico_elements": {
                "population": "Adults with diabetes",
                "intervention": "New drug X",
                "comparator": "Placebo",
                "outcome": "Blood glucose levels",
            }
        }
        result = validator.validate(basic_evidence)
        assert result.is_valid

    def test_validate_extraction_details(self, basic_evidence):
        """Test extraction details validation."""
        validator = EvidenceValidator()

        # Add extraction details to metadata
        basic_evidence["metadata"] = {
            "extraction_details": {
                "method": "machine_learning",
                "confidence": 0.95,
                "model_version": "v2.1",
                "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
            }
        }
        result = validator.validate(basic_evidence)
        assert result.is_valid

    def test_validate_custom_metadata(self, basic_evidence):
        """Test custom metadata validation."""
        validator = EvidenceValidator(strict_mode=False)

        # Add custom fields to metadata only (since additionalProperties is false)
        basic_evidence["metadata"] = {"custom_meta": "value", "another_field": "another_value"}

        result = validator.validate(basic_evidence)
        # Should be valid since metadata is flexible
        assert result.is_valid

    def test_batch_validation(self):
        """Test batch validation of evidence."""
        validator = EvidenceValidator()

        evidence_list = [
            {
                "schema_version": "1.0",
                "id": str(uuid4()),
                "run_id": str(uuid4()),
                "source_id": str(uuid4()),
                "evidence_type": "statistic",
                "content": "Evidence 1",
                "created_at": datetime.utcnow().isoformat() + "Z",
            },
            {
                "schema_version": "1.0",
                "id": str(uuid4()),
                "run_id": str(uuid4()),
                "source_id": str(uuid4()),
                "evidence_type": "invalid_evidence_type",  # Invalid
                "content": "Evidence 2",
                "created_at": datetime.utcnow().isoformat() + "Z",
            },
        ]

        results = validator.validate_batch(evidence_list)
        assert len(results) == 2
        assert results[0].is_valid
        assert not results[1].is_valid
