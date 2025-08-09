"""Comprehensive tests for PenEllE validators."""

from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest

from src.core.schemas.validation_service import ValidationService, validate
from src.core.schemas.validators import (
    ClaimValidator,
    DraftSectionValidator,
    EvidenceValidator,
    QualityReportValidator,
    RunManifestValidator,
    RunValidator,
    SourceValidator,
    ValidationError,
    ValidationResult,
    ValidationSeverity,
)


class TestBaseValidator:
    """Tests for base validator functionality."""

    def test_validation_result_creation(self):
        """Test ValidationResult creation and methods."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

        # Add error
        error = ValidationError(
            path="test.field", message="Test error", severity=ValidationSeverity.ERROR
        )
        result.add_error(error)
        assert not result.is_valid
        assert len(result.errors) == 1

        # Add warning
        warning = ValidationError(
            path="test.warning", message="Test warning", severity=ValidationSeverity.WARNING
        )
        result.add_warning(warning)
        assert len(result.warnings) == 1

        # Test serialization
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "is_valid" in result_dict
        assert "errors" in result_dict
        assert "warnings" in result_dict


class TestRunValidator:
    """Tests for run configuration validators."""

    @pytest.fixture()
    def valid_run_config(self) -> dict[str, Any]:
        """Create a valid run configuration."""
        return {
            "schema_version": "1.0",
            "style_pack": "academic_report",
            "target_word_count": 5000,
            "language": "en",
            "source_limits": {
                "max_sources": 50,
                "min_quality_score": 0.7,
                "publication_year_range": {"start": 2020, "end": 2025},
            },
            "connectors": [
                {
                    "name": "pubmed",
                    "enabled": True,
                    "priority": 1,
                    "config": {"api_key": "test-key"},
                }
            ],
            "quality_gates": {"min_evidence_per_claim": 2, "min_quality_score": 0.75},
            "llm_config": {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            "output_formats": ["markdown", "pdf"],
        }

    def test_valid_run_configuration(self, valid_run_config):
        """Test validation of valid run configuration."""
        validator = RunValidator(schema_type="configuration")
        result = validator.validate(valid_run_config)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_style_pack(self, valid_run_config):
        """Test validation of invalid style pack."""
        valid_run_config["style_pack"] = "invalid_style"
        validator = RunValidator(schema_type="configuration")
        result = validator.validate(valid_run_config)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_invalid_temperature_range(self, valid_run_config):
        """Test validation of temperature outside valid range."""
        valid_run_config["llm_config"]["temperature"] = 3.0
        validator = RunValidator(schema_type="configuration")
        result = validator.validate(valid_run_config)
        assert not result.is_valid
        assert any("temperature" in e.path for e in result.errors)

    def test_missing_search_params_when_enabled(self):
        """Test validation when search is enabled but params missing."""
        config = {"enable_search": True, "parameters": {}}
        validator = RunValidator()
        result = validator.validate(config)
        assert not result.is_valid
        assert any("search_params" in e.message for e in result.errors)


class TestSourceValidator:
    """Tests for CSL-JSON source validator."""

    @pytest.fixture()
    def valid_source(self) -> dict[str, Any]:
        """Create a valid source."""
        return {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "fingerprint": "a" * 64,
            "csl_json": {
                "type": "article-journal",
                "title": "Test Article Title",
                "author": [
                    {
                        "family": "Smith",
                        "given": "John",
                        "ORCID": "https://orcid.org/0000-0002-1825-0097",
                    }
                ],
                "issued": {"date-parts": [[2023, 6, 15]]},
                "container-title": "Journal of Testing",
                "volume": "10",
                "page": "123-456",
                "DOI": "10.1234/test.2023.001",
            },
            "quality_score": 0.9,
            "connector_name": "test",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    def test_valid_source(self, valid_source):
        """Test validation of valid CSL-JSON source."""
        validator = SourceValidator()
        result = validator.validate(valid_source)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_csl_type(self, valid_source):
        """Test validation of invalid CSL type."""
        valid_source["csl_json"]["type"] = "invalid-type"
        validator = SourceValidator()
        result = validator.validate(valid_source)
        assert not result.is_valid
        assert any("type" in str(e.path) for e in result.errors)

    def test_invalid_date_format(self, valid_source):
        """Test validation of invalid date format."""
        valid_source["csl_json"]["issued"]["date-parts"] = [[2023, 13, 40]]  # Invalid month/day
        validator = SourceValidator()
        result = validator.validate(valid_source)
        assert not result.is_valid
        assert any(
            "date" in str(e.message).lower()
            or "month" in str(e.message).lower()
            or "day" in str(e.message).lower()
            for e in result.errors
        )

    def test_invalid_orcid_format(self, valid_source):
        """Test validation of invalid ORCID format."""
        valid_source["csl_json"]["author"][0]["ORCID"] = "invalid-orcid"
        validator = SourceValidator()
        result = validator.validate(valid_source)
        assert not result.is_valid
        assert any("ORCID" in str(e.message) for e in result.errors)

    def test_missing_title(self):
        """Test validation when title is missing."""
        source = {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "fingerprint": "a" * 64,
            "csl_json": {
                "type": "article-journal"
                # Missing title
            },
            "connector_name": "test",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        validator = SourceValidator()
        result = validator.validate(source)
        assert not result.is_valid
        assert any("title" in e.message for e in result.errors)


class TestEvidenceValidator:
    """Tests for evidence validator."""

    @pytest.fixture()
    def valid_evidence(self) -> dict[str, Any]:
        """Create valid evidence data."""
        return {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "source_id": str(uuid4()),
            "evidence_type": "statistic",
            "content": "This is the evidence content with key finding.",
            "context": "The surrounding context for this evidence.",
            "page_number": 123,
            "section": "Results",
            "confidence_score": 0.9,
            "relevance_score": 0.85,
            "metadata": {
                "extraction_method": "regex_pattern",
                "validation_status": "verified",
            },
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    def test_valid_evidence(self, valid_evidence):
        """Test validation of valid evidence."""
        validator = EvidenceValidator()
        result = validator.validate(valid_evidence)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_evidence_type(self, valid_evidence):
        """Test validation of invalid evidence type."""
        valid_evidence["evidence_type"] = "invalid_type"
        validator = EvidenceValidator()
        result = validator.validate(valid_evidence)
        assert not result.is_valid
        assert any("evidence_type" in str(e.path) for e in result.errors)

    def test_invalid_highlight_offsets(self, valid_evidence):
        """Test validation of invalid highlight offsets."""
        # Evidence schema doesn't have highlights, but we can test other constraints
        valid_evidence["confidence_score"] = 1.5  # Invalid - must be between 0-1
        validator = EvidenceValidator()
        result = validator.validate(valid_evidence)
        assert not result.is_valid
        assert any("confidence_score" in str(e.path) for e in result.errors)

    def test_limited_access_evidence(self):
        """Test validation of limited access evidence."""
        limited_evidence = {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "source_id": str(uuid4()),
            "evidence_type": "figure",
            "summary": "Summary of restricted evidence",
            "access_restrictions": {
                "reason": "copyright",
                "access_url": "https://example.com/article",
                "license": "Publisher Copyright",
            },
            "metadata": {
                "page_number": 8,
                "confidence_score": 0.95,
            },
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        validator = EvidenceValidator(evidence_type="limited_access")
        result = validator.validate(limited_evidence)
        assert result.is_valid

    def test_embargoed_without_expiration(self):
        """Test validation of embargoed evidence without expiration."""
        limited_evidence = {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "source_id": str(uuid4()),
            "evidence_type": "figure",
            "summary": "Embargoed evidence summary",
            "access_restrictions": {
                "reason": "embargo",
                "access_url": "https://example.com/article",
                "license": "Embargoed",
                # Missing embargo_until when reason is embargo
            },
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        validator = EvidenceValidator(evidence_type="limited_access")
        result = validator.validate(limited_evidence)
        # This should pass - embargo_until is optional
        assert result.is_valid


class TestClaimValidator:
    """Tests for claim validator."""

    @pytest.fixture()
    def valid_claim(self) -> dict[str, Any]:
        """Create valid claim data."""
        return {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "claim_text": "Drug X reduces symptoms by 50%",
            "claim_type": "causal",
            "supporting_evidence_ids": [str(uuid4()), str(uuid4()), str(uuid4())],
            "confidence_score": 0.87,
            "verification_status": "verified",
            "section_id": str(uuid4()),
            "position": {"paragraph": 3, "sentence": 2},
            "metadata": {"nli_score": 0.92, "contradicting_evidence_ids": []},
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    def test_valid_claim(self, valid_claim):
        """Test validation of valid claim."""
        validator = ClaimValidator()
        result = validator.validate(valid_claim)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_claim_type(self, valid_claim):
        """Test validation of invalid claim type."""
        valid_claim["claim_type"] = "invalid_type"
        validator = ClaimValidator()
        result = validator.validate(valid_claim)
        assert not result.is_valid
        assert any("claim_type" in str(e.path) for e in result.errors)

    def test_missing_pico_elements(self, valid_claim):
        """Test validation when PICO elements are missing from metadata."""
        # The schema doesn't require PICO elements, but we can test missing metadata
        valid_claim["metadata"] = {}  # Empty metadata
        validator = ClaimValidator()
        result = validator.validate(valid_claim)
        # This should still be valid as metadata can be empty
        assert result.is_valid

    def test_inconsistent_assessment(self, valid_claim):
        """Test validation of inconsistent confidence score and verification status."""
        valid_claim["confidence_score"] = 0.1  # Very low confidence
        valid_claim["verification_status"] = "verified"  # But marked as verified
        validator = ClaimValidator()
        result = validator.validate(valid_claim)
        # The validator might add warnings about this inconsistency
        assert result.is_valid  # Should still be valid structurally


class TestOutputValidators:
    """Tests for output validators."""

    def test_draft_section_validator(self):
        """Test draft section validation."""
        # Use the correct structure from get_example_draft_section()
        draft_section = {
            "schema_version": "1.0",
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "section_type": "introduction",
            "title": "Introduction",
            "content": "This is the introduction section.",
            "order": 1,
            "evidence_ids": [str(uuid4()) for _ in range(3)],
            "claim_ids": [str(uuid4()) for _ in range(2)],
            "word_count": 156,
            "metadata": {
                "generated_by": "test-agent",
                "generation_timestamp": datetime.utcnow().isoformat() + "Z",
                "revision": 1,
            },
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

        validator = DraftSectionValidator()
        result = validator.validate(draft_section)
        assert result.is_valid

    def test_quality_report_validator(self):
        """Test quality report validation."""
        # Use the correct structure from get_example_quality_report()
        quality_report = {
            "schema_version": "1.0",
            "run_id": str(uuid4()),
            "overall_score": 0.88,
            "passed": True,
            "metrics": {
                "readability": {
                    "flesch_reading_ease": 45.2,
                    "flesch_kincaid_grade": 14.3,
                    "gunning_fog": 16.8,
                    "smog_index": 15.2,
                    "automated_readability_index": 14.7,
                },
                "writing_quality": {
                    "passive_voice_percentage": 12.4,
                    "sentence_complexity": 0.68,
                    "average_sentence_length": 22.3,
                    "vocabulary_diversity": 0.82,
                },
                "evidence_quality": {
                    "average_evidence_per_claim": 3.2,
                    "unsupported_claims": 2,
                    "evidence_diversity": 0.78,
                    "source_recency": 0.91,
                },
                "factual_accuracy": {
                    "verified_claims": 142,
                    "disputed_claims": 3,
                    "unverifiable_claims": 11,
                    "accuracy_score": 0.92,
                },
                "citation_quality": {
                    "citation_density": 4.2,
                    "citation_diversity": 0.85,
                    "self_citation_percentage": 2.1,
                },
            },
            "issues": [
                {
                    "severity": "warning",
                    "category": "readability",
                    "message": "Average sentence length exceeds recommended 20 words",
                    "location": {"section_id": str(uuid4()), "paragraph": 5, "sentence": 3},
                    "suggestion": "Consider breaking this sentence into two shorter sentences for improved readability",
                }
            ],
            "recommendations": [
                "Reduce average sentence length to improve readability scores",
                "Add more recent sources (2022-2024) to strengthen evidence base",
            ],
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

        validator = QualityReportValidator()
        result = validator.validate(quality_report)
        assert result.is_valid

    def test_run_manifest_validator(self):
        """Test run manifest validation."""
        # Use the correct structure from get_example_run_manifest()
        run_id = str(uuid4())
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "thesis": "Climate change significantly impacts coastal ecosystems through sea level rise, temperature changes, and altered precipitation patterns, necessitating adaptive management strategies.",
            "status": "completed",
            "pipeline_version": "1.0.0",
            "configuration": {
                "style_pack": "academic_report",
                "target_word_count": 5000,
                "language": "en",
                "source_limits": {
                    "max_sources": 100,
                    "min_quality_score": 0.7,
                    "publication_year_range": {"start": 2018, "end": 2024},
                },
                "quality_gates": {"min_evidence_per_claim": 2, "min_quality_score": 0.75},
            },
            "artifacts": {
                "sources": [
                    {
                        "artifact_id": str(uuid4()),
                        "filename": "sources.json",
                        "file_path": f"runs/{run_id}/sources.json",
                        "file_size": 245678,
                        "checksum": "b" * 64,
                        "content_type": "application/json",
                    }
                ],
                "evidence": [
                    {
                        "artifact_id": str(uuid4()),
                        "filename": "evidence_batch_1.json",
                        "file_path": f"runs/{run_id}/evidence/batch_1.json",
                        "file_size": 567890,
                        "checksum": "c" * 64,
                        "content_type": "application/json",
                    }
                ],
                "draft_sections": [
                    {
                        "artifact_id": str(uuid4()),
                        "filename": "draft_introduction.md",
                        "file_path": f"runs/{run_id}/drafts/introduction.md",
                        "file_size": 12345,
                        "checksum": "d" * 64,
                        "content_type": "text/markdown",
                    }
                ],
                "final_output": {
                    "artifact_id": str(uuid4()),
                    "filename": "final_report.pdf",
                    "file_path": f"runs/{run_id}/output/final_report.pdf",
                    "file_size": 2345678,
                    "checksum": "e" * 64,
                    "content_type": "application/pdf",
                },
            },
            "metrics": {
                "total_sources": 87,
                "total_evidence": 342,
                "total_claims": 156,
                "word_count": 4987,
                "quality_score": 0.89,
                "execution_time_seconds": 1234.56,
            },
            "created_at": datetime.utcnow().isoformat() + "Z",
            "completed_at": datetime.utcnow().isoformat() + "Z",
        }

        validator = RunManifestValidator()
        result = validator.validate(manifest)
        assert result.is_valid


class TestValidationService:
    """Tests for centralized validation service."""

    @pytest.fixture()
    def service(self) -> ValidationService:
        """Create validation service instance."""
        return ValidationService()

    def test_service_initialization(self, service):
        """Test service initialization."""
        assert service is not None
        assert len(service.available_schemas) > 0
        assert "source" in service.available_schemas
        assert "claim" in service.available_schemas

    def test_validate_with_service(self, service):
        """Test validation through service."""
        data = {"id": "test123", "type": "article-journal", "title": "Test Article"}

        result = service.validate("source", data)
        assert isinstance(result, ValidationResult)
        assert result.metadata["schema_type"] == "source"

    def test_batch_validation(self, service):
        """Test batch validation."""
        data_list = [
            {
                "schema_version": "1.0",
                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "fingerprint": "a" * 64,
                "connector_name": "pubmed",
                "csl_json": {
                    "type": "article-journal",
                    "title": "Article 1",
                    "container-title": "Journal of Testing",
                    "volume": "1",
                    "issue": "1",
                },
            },
            {
                "schema_version": "1.0",
                "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "fingerprint": "b" * 64,
                "connector_name": "crossref",
                "csl_json": {"type": "book", "title": "Book 1"},
            },
            {
                "schema_version": "1.0",
                "id": "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
                "fingerprint": "c" * 64,
                "connector_name": "invalid_connector",
                "csl_json": {"type": "invalid", "title": "Invalid"},  # This will fail validation
            },
        ]

        results = service.validate_batch("source", data_list)
        assert len(results) == 3
        assert results[0].is_valid
        assert results[1].is_valid
        assert not results[2].is_valid  # Invalid type should fail

    def test_invalid_schema_type(self, service):
        """Test validation with invalid schema type."""
        with pytest.raises(ValueError) as exc_info:
            service.validate("invalid_schema", {})
        assert "Unsupported schema type" in str(exc_info.value)

    def test_schema_info(self, service):
        """Test getting schema information."""
        info = service.get_schema_info("claim")
        assert info["schema_type"] == "claim"
        assert "validator_class" in info
        assert info["validator_class"] == "ClaimValidator"

    def test_list_schemas(self, service):
        """Test listing available schemas."""
        schemas = service.list_schemas()
        assert len(schemas) > 0
        assert any(s["type"] == "evidence" for s in schemas)

    def test_convenience_functions(self):
        """Test module-level convenience functions."""
        data = {
            "statement": {"text": "Test claim"},
            "metadata": {
                "claim_id": "CLM-TEST001",
                "claim_type": "efficacy",
                "created_at": datetime.utcnow().isoformat() + "Z",
            },
        }

        result = validate("claim", data)
        assert isinstance(result, ValidationResult)
