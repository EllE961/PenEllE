"""Comprehensive tests for JSON schemas and Pydantic models."""

import json
from datetime import datetime
from uuid import uuid4

import pytest
from jsonschema import ValidationError

from src.core.schemas import models
from src.core.schemas.examples.examples import (
    get_example_bibliography,
    get_example_claim,
    get_example_draft_section,
    get_example_event_envelope,
    get_example_evidence,
    get_example_limited_access_evidence,
    get_example_quality_report,
    get_example_run_configuration,
    get_example_run_manifest,
    get_example_search_result,
    get_example_source,
    get_example_structured_input,
)
from src.core.schemas.registry import SchemaRegistry, get_registry


class TestSchemaRegistry:
    """Test the schema registry functionality."""

    def test_registry_initialization(self):
        """Test that registry initializes and loads all schemas."""
        registry = SchemaRegistry()
        schemas = registry.get_all_schemas()

        # Should have all 12 schemas
        assert len(schemas) == 12

        # Check all expected schemas are present
        expected_schemas = [
            "source",
            "evidence",
            "claim",
            "draft_section",
            "run_manifest",
            "run_configuration",
            "quality_report",
            "event_envelope",
            "search_result",
            "bibliography",
            "structured_input",
            "limited_access_evidence",
        ]

        for schema_name in expected_schemas:
            assert schema_name in schemas
            assert schemas[schema_name]["$schema"] == "http://json-schema.org/draft-07/schema#"
            assert schemas[schema_name]["properties"]["schema_version"]["const"] == "1.0"

    def test_load_schema(self):
        """Test loading individual schemas."""
        registry = get_registry()

        # Test loading existing schema
        schema = registry.load_schema("source")
        assert schema["title"] == "Source"
        assert "csl_json" in schema["properties"]

        # Test loading non-existent schema
        with pytest.raises(KeyError, match="Schema 'nonexistent' not found"):
            registry.load_schema("nonexistent")

    def test_validate_json_valid(self):
        """Test validating valid JSON data."""
        registry = get_registry()

        # Test with dict
        valid_data = get_example_source()
        result = registry.validate_json(valid_data, "source")
        assert result == valid_data

        # Test with JSON string
        json_string = json.dumps(valid_data)
        result = registry.validate_json(json_string, "source")
        assert result == valid_data

    def test_validate_json_invalid(self):
        """Test validating invalid JSON data."""
        registry = get_registry()

        # Missing required field
        invalid_data = {
            "schema_version": "1.0",
            "id": str(uuid4()),
            # Missing fingerprint and other required fields
        }

        with pytest.raises(ValidationError, match="fingerprint"):
            registry.validate_json(invalid_data, "source")

        # Invalid field value
        invalid_data = get_example_source()
        invalid_data["fingerprint"] = "invalid"  # Should be 64 hex chars

        with pytest.raises(ValidationError, match="fingerprint"):
            registry.validate_json(invalid_data, "source")

    def test_get_pydantic_model(self):
        """Test getting Pydantic model classes."""
        registry = get_registry()

        # Test existing mapping
        model_class = registry.get_pydantic_model("source")
        assert model_class == models.Source

        # Test non-existent mapping
        assert registry.get_pydantic_model("nonexistent") is None

    def test_validate_with_model(self):
        """Test validating data and getting Pydantic model instance."""
        registry = get_registry()

        # Test successful validation
        data = get_example_source()
        model_instance = registry.validate_with_model(data, "source")
        assert isinstance(model_instance, models.Source)
        assert str(model_instance.id) == data["id"]
        assert model_instance.fingerprint == data["fingerprint"]

        # Test with invalid data
        invalid_data = {"schema_version": "1.0"}
        with pytest.raises(ValidationError):
            registry.validate_with_model(invalid_data, "source")

    def test_to_json_schema(self):
        """Test converting Pydantic model to JSON-schema validated dict."""
        registry = get_registry()

        # Create model instance
        source = models.Source(
            id=uuid4(),
            fingerprint="a" * 64,
            csl_json=models.CSLJSON(
                type="article-journal",
                title="Test Article",
                author=[models.CSLAuthor(family="Doe", given="John")],
            ),
            quality_score=0.9,
            connector_name="test",
            created_at=datetime.utcnow(),
        )

        # Convert to JSON schema
        json_data = registry.to_json_schema(source)

        # Should pass validation
        validated = registry.validate_json(json_data, "source")
        assert validated["fingerprint"] == source.fingerprint


class TestSchemaExamples:
    """Test that all example data validates against schemas."""

    def test_source_example(self):
        """Test source example validates."""
        registry = get_registry()
        example = get_example_source()

        # Validate against JSON schema
        registry.validate_json(example, "source")

        # Create Pydantic model
        model = registry.validate_with_model(example, "source")
        assert isinstance(model, models.Source)
        assert model.quality_score == 0.92

    def test_evidence_example(self):
        """Test evidence example validates."""
        registry = get_registry()
        example = get_example_evidence()

        registry.validate_json(example, "evidence")
        model = registry.validate_with_model(example, "evidence")
        assert isinstance(model, models.Evidence)
        assert model.evidence_type == models.EvidenceType.STATISTIC

    def test_claim_example(self):
        """Test claim example validates."""
        registry = get_registry()
        example = get_example_claim()

        registry.validate_json(example, "claim")
        model = registry.validate_with_model(example, "claim")
        assert isinstance(model, models.Claim)
        assert model.claim_type == models.ClaimType.CAUSAL

    def test_draft_section_example(self):
        """Test draft section example validates."""
        registry = get_registry()
        example = get_example_draft_section()

        registry.validate_json(example, "draft_section")
        model = registry.validate_with_model(example, "draft_section")
        assert isinstance(model, models.DraftSection)
        assert model.section_type == models.SectionType.INTRODUCTION

    def test_run_manifest_example(self):
        """Test run manifest example validates."""
        registry = get_registry()
        example = get_example_run_manifest()

        registry.validate_json(example, "run_manifest")
        model = registry.validate_with_model(example, "run_manifest")
        assert isinstance(model, models.RunManifest)
        assert model.status == models.RunStatus.COMPLETED

    def test_run_configuration_example(self):
        """Test run configuration example validates."""
        registry = get_registry()
        example = get_example_run_configuration()

        registry.validate_json(example, "run_configuration")
        model = registry.validate_with_model(example, "run_configuration")
        assert isinstance(model, models.RunConfiguration)
        assert model.style_pack == models.StylePack.ACADEMIC_REPORT

    def test_quality_report_example(self):
        """Test quality report example validates."""
        registry = get_registry()
        example = get_example_quality_report()

        registry.validate_json(example, "quality_report")
        model = registry.validate_with_model(example, "quality_report")
        assert isinstance(model, models.QualityReport)
        assert model.overall_score == 0.88

    def test_event_envelope_example(self):
        """Test event envelope example validates."""
        registry = get_registry()
        example = get_example_event_envelope()

        registry.validate_json(example, "event_envelope")
        model = registry.validate_with_model(example, "event_envelope")
        assert isinstance(model, models.EventEnvelope)
        assert model.event_type == "stage_completed"

    def test_search_result_example(self):
        """Test search result example validates."""
        registry = get_registry()
        example = get_example_search_result()

        registry.validate_json(example, "search_result")
        model = registry.validate_with_model(example, "search_result")
        assert isinstance(model, models.SearchResult)
        assert model.relevance_score == 0.94

    def test_bibliography_example(self):
        """Test bibliography example validates."""
        registry = get_registry()
        example = get_example_bibliography()

        registry.validate_json(example, "bibliography")
        model = registry.validate_with_model(example, "bibliography")
        assert isinstance(model, models.Bibliography)
        assert model.citation_style == models.CitationStyle.APA

    def test_structured_input_example(self):
        """Test structured input example validates."""
        registry = get_registry()
        example = get_example_structured_input()

        registry.validate_json(example, "structured_input")
        model = registry.validate_with_model(example, "structured_input")
        assert isinstance(model, models.StructuredInput)
        assert len(model.objectives) == 4

    def test_limited_access_evidence_example(self):
        """Test limited access evidence example validates."""
        registry = get_registry()
        example = get_example_limited_access_evidence()

        registry.validate_json(example, "limited_access_evidence")
        model = registry.validate_with_model(example, "limited_access_evidence")
        assert isinstance(model, models.LimitedAccessEvidence)
        assert model.access_restrictions.reason == "copyright"


class TestPydanticModels:
    """Test Pydantic model validation and behavior."""

    def test_enum_validation(self):
        """Test that enums validate correctly."""
        # Valid enum
        evidence = models.Evidence(
            id=uuid4(),
            run_id=uuid4(),
            source_id=uuid4(),
            evidence_type=models.EvidenceType.STATISTIC,
            content="Test content",
            created_at=datetime.utcnow(),
        )
        assert evidence.evidence_type == models.EvidenceType.STATISTIC

        # Invalid enum value should raise error
        with pytest.raises(ValueError):
            models.Evidence(
                id=uuid4(),
                run_id=uuid4(),
                source_id=uuid4(),
                evidence_type="invalid_type",  # type: ignore
                content="Test content",
                created_at=datetime.utcnow(),
            )

    def test_field_validation(self):
        """Test field validation rules."""
        # Test quality score range
        with pytest.raises(ValueError):
            models.Source(
                id=uuid4(),
                fingerprint="a" * 64,
                csl_json={"type": "article", "title": "Test"},
                quality_score=1.5,  # Should be 0-1
                connector_name="test",
                created_at=datetime.utcnow(),
            )

        # Test fingerprint pattern
        with pytest.raises(ValueError):
            models.Source(
                id=uuid4(),
                fingerprint="invalid",  # Should be 64 hex chars
                csl_json={"type": "article", "title": "Test"},
                connector_name="test",
                created_at=datetime.utcnow(),
            )

    def test_csl_json_alias(self):
        """Test that CSL-JSON fields use proper aliases."""
        csl = models.CSLJSON(
            type="article-journal",
            title="Test Article",
            container_title="Test Journal",
            issued=models.CSLDate(date_parts=[[2023, 6, 15]]),
        )

        # Check serialization uses aliases
        json_data = csl.model_dump(mode="json", by_alias=True)
        assert "container-title" in json_data
        assert "container_title" not in json_data
        assert "date-parts" in json_data["issued"]

    def test_optional_fields(self):
        """Test that optional fields work correctly."""
        # Minimal required fields only
        source = models.Source(
            id=uuid4(),
            fingerprint="a" * 64,
            csl_json={"type": "article", "title": "Test"},
            connector_name="test",
            created_at=datetime.utcnow(),
        )
        assert source.quality_score is None
        assert source.raw_metadata is None

        # With optional fields
        source_full = models.Source(
            id=uuid4(),
            fingerprint="b" * 64,
            csl_json={"type": "article", "title": "Test"},
            quality_score=0.85,
            relevance_score=0.90,
            connector_name="test",
            raw_metadata={"extra": "data"},
            created_at=datetime.utcnow(),
        )
        assert source_full.quality_score == 0.85
        assert source_full.raw_metadata == {"extra": "data"}

    def test_schema_version_constant(self):
        """Test that schema version defaults to 1.0."""
        source = models.Source(
            id=uuid4(),
            fingerprint="a" * 64,
            csl_json={"type": "article", "title": "Test"},
            connector_name="test",
            created_at=datetime.utcnow(),
        )
        assert source.schema_version == "1.0"

        # Trying to create with different version should fail due to Literal type
        with pytest.raises(ValueError):
            models.Source(
                id=uuid4(),
                fingerprint="a" * 64,
                csl_json={"type": "article", "title": "Test"},
                connector_name="test",
                created_at=datetime.utcnow(),
                schema_version="2.0",  # Should fail validation
            )


class TestDatabaseModelIntegration:
    """Test integration between database models and schema models."""

    def test_source_to_from_schema(self):
        """Test converting Source between DB and schema models."""
        from src.core.database.models import Source as DBSource

        # Create schema model
        schema_source = models.Source(
            id=uuid4(),
            fingerprint="a" * 64,
            csl_json=models.CSLJSON(
                type="article-journal",
                title="Test Article",
                author=[models.CSLAuthor(family="Doe", given="John")],
            ),
            quality_score=0.9,
            connector_name="test",
            created_at=datetime.utcnow(),
        )

        # Convert to DB model
        run_id = uuid4()
        db_source = DBSource.from_schema(schema_source, run_id)
        assert db_source.id == schema_source.id
        assert db_source.run_id == run_id
        assert db_source.fingerprint == schema_source.fingerprint

        # Convert back to schema
        schema_back = db_source.to_schema()
        assert schema_back.id == schema_source.id
        assert schema_back.fingerprint == schema_source.fingerprint

    def test_evidence_to_from_schema(self):
        """Test converting Evidence between DB and schema models."""
        from src.core.database.models import Evidence as DBEvidence

        # Create schema model
        schema_evidence = models.Evidence(
            id=uuid4(),
            run_id=uuid4(),
            source_id=uuid4(),
            evidence_type=models.EvidenceType.QUOTE,
            content="Test quote",
            context="Test context",
            page_number=42,
            section="Results",
            confidence_score=0.85,
            created_at=datetime.utcnow(),
        )

        # Convert to DB model
        db_evidence = DBEvidence.from_schema(schema_evidence)
        assert db_evidence.id == schema_evidence.id
        assert db_evidence.evidence_type == "quote"
        assert db_evidence.location["page"] == 42
        assert db_evidence.location["section"] == "Results"

        # Convert back to schema
        schema_back = db_evidence.to_schema()
        assert schema_back.id == schema_evidence.id
        assert schema_back.evidence_type == models.EvidenceType.QUOTE
        assert schema_back.page_number == 42


class TestSchemaValidationEdgeCases:
    """Test edge cases and error conditions."""

    def test_invalid_uuid_format(self):
        """Test that invalid UUID format is rejected."""
        registry = get_registry()

        invalid_data = get_example_source()
        invalid_data["id"] = "not-a-uuid"

        with pytest.raises(ValidationError, match="uuid"):
            registry.validate_json(invalid_data, "source")

    def test_invalid_datetime_format(self):
        """Test that invalid datetime format is rejected."""
        registry = get_registry()

        invalid_data = get_example_source()
        invalid_data["created_at"] = "2023-13-45"  # Invalid date

        with pytest.raises(ValidationError, match="date-time"):
            registry.validate_json(invalid_data, "source")

    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected."""
        registry = get_registry()

        invalid_data = get_example_source()
        invalid_data["extra_field"] = "should not be here"

        with pytest.raises(ValidationError, match="Additional properties are not allowed"):
            registry.validate_json(invalid_data, "source")

    def test_wrong_schema_version(self):
        """Test that wrong schema version is rejected."""
        registry = get_registry()

        invalid_data = get_example_source()
        invalid_data["schema_version"] = "2.0"

        with pytest.raises(ValidationError, match="schema_version"):
            registry.validate_json(invalid_data, "source")

    def test_nested_validation(self):
        """Test that nested objects are validated."""
        registry = get_registry()

        # Invalid CSL-JSON in source
        invalid_data = get_example_source()
        invalid_data["csl_json"]["type"] = ""  # Empty type

        # Should fail validation
        with pytest.raises(ValidationError):
            registry.validate_with_model(invalid_data, "source")
