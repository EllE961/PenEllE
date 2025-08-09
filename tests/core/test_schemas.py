"""Tests for JSON schema validity and structure."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, SchemaError


class TestSchemaValidity:
    """Test that all JSON schemas are valid according to JSON Schema spec."""

    @pytest.fixture()
    def schema_dir(self):
        """Get the schemas directory."""
        return Path(__file__).parent.parent.parent / "src" / "core" / "schemas" / "json"

    @pytest.fixture()
    def all_schemas(self, schema_dir):
        """Load all JSON schemas."""
        schemas = {}
        for schema_file in schema_dir.glob("*.json"):
            with open(schema_file) as f:
                schemas[schema_file.stem] = json.load(f)
        return schemas

    def test_all_schemas_exist(self, all_schemas):
        """Test that all required schemas exist."""
        required_schemas = [
            "source",
            "evidence",
            "draft_section",
            "claim",
            "run_manifest",
            "limited_access_evidence",
            "run_configuration",
            "structured_input",
            "search_result",
            "quality_report",
            "event_envelope",
            "bibliography",
        ]

        for schema_name in required_schemas:
            assert schema_name in all_schemas, f"Missing schema: {schema_name}.json"

        assert len(all_schemas) == 12, f"Expected 12 schemas, found {len(all_schemas)}"

    def test_schemas_are_valid_json_schema(self, all_schemas):
        """Test that all schemas are valid JSON Schema documents."""
        for name, schema in all_schemas.items():
            try:
                Draft7Validator.check_schema(schema)
            except SchemaError as e:
                pytest.fail(f"Schema '{name}' is not valid: {e}")

    def test_schemas_have_required_fields(self, all_schemas):
        """Test that schemas have required metadata fields."""
        for name, schema in all_schemas.items():
            assert "$schema" in schema, f"Schema '{name}' missing $schema"
            assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"

            assert "title" in schema, f"Schema '{name}' missing title"
            assert "description" in schema, f"Schema '{name}' missing description"
            assert "type" in schema, f"Schema '{name}' missing type"

    def test_source_schema_csl_compatibility(self, all_schemas):
        """Test that source schema is CSL-JSON compatible."""
        source_schema = all_schemas["source"]

        # Check that csl_json is present
        properties = source_schema.get("properties", {})
        assert "csl_json" in properties, "Source schema missing csl_json field"

        # Check for CSL required fields within csl_json
        csl_json_props = properties["csl_json"].get("properties", {})
        csl_fields = ["type", "title"]  # Only type and title are required in CSL-JSON

        for field in csl_fields:
            assert field in csl_json_props, f"Source schema csl_json missing CSL field: {field}"

    def test_evidence_schema_has_type_enum(self, all_schemas):
        """Test that evidence schema has correct type enum."""
        evidence_schema = all_schemas["evidence"]

        # Check evidence_type field
        type_property = evidence_schema.get("properties", {}).get("evidence_type", {})
        assert "enum" in type_property, "Evidence schema evidence_type should have enum"

        # The actual types in our schema
        expected_types = ["statistic", "quote", "method", "casestudy", "table", "figure"]
        actual_types = type_property["enum"]

        # Check that we have the expected types
        assert set(expected_types).issubset(
            set(actual_types)
        ), "Evidence type enum missing some expected types"

    def test_claim_schema_has_evidence_links(self, all_schemas):
        """Test that claim schema includes evidence linking."""
        claim_schema = all_schemas["claim"]

        properties = claim_schema.get("properties", {})
        assert (
            "supporting_evidence_ids" in properties
        ), "Claim schema missing supporting_evidence_ids"

        evidence_ids = properties["supporting_evidence_ids"]
        assert evidence_ids.get("type") == "array", "supporting_evidence_ids should be array type"

    def test_run_configuration_completeness(self, all_schemas):
        """Test that run configuration has all required options."""
        config_schema = all_schemas["run_configuration"]

        properties = config_schema.get("properties", {})

        # Check for our actual configuration structure
        assert "source_limits" in properties, "Run configuration missing source_limits"
        assert "quality_gates" in properties, "Run configuration missing quality_gates"
        assert "llm_config" in properties, "Run configuration missing llm_config"
        assert "output_formats" in properties, "Run configuration missing output_formats"

        # Check nested properties
        source_limits = properties["source_limits"].get("properties", {})
        assert "max_sources" in source_limits, "source_limits missing max_sources"

    def test_quality_report_metrics(self, all_schemas):
        """Test that quality report has all metric categories."""
        quality_schema = all_schemas["quality_report"]

        properties = quality_schema.get("properties", {})
        assert "metrics" in properties, "Quality report missing metrics"
        assert "overall_score" in properties, "Quality report missing overall_score"

        metrics_properties = properties["metrics"].get("properties", {})
        metric_categories = [
            "readability",
            "writing_quality",
            "evidence_quality",
            "factual_accuracy",
            "citation_quality",
        ]

        for category in metric_categories:
            assert category in metrics_properties, f"Quality report missing metric: {category}"

    def test_event_envelope_structure(self, all_schemas):
        """Test event envelope has proper event system structure."""
        event_schema = all_schemas["event_envelope"]

        properties = event_schema.get("properties", {})
        required_fields = ["event_id", "event_type", "timestamp", "payload", "metadata"]

        for field in required_fields:
            assert field in properties, f"Event envelope missing field: {field}"

    def test_bibliography_format(self, all_schemas):
        """Test bibliography schema structure."""
        bib_schema = all_schemas["bibliography"]

        properties = bib_schema.get("properties", {})
        assert "entries" in properties, "Bibliography missing entries"

        entries = properties["entries"]
        assert entries.get("type") == "array", "Bibliography entries should be array"
        assert "items" in entries, "Bibliography entries missing items definition"


class TestSchemaReferences:
    """Test schema cross-references and dependencies."""

    @pytest.fixture()
    def schema_dir(self):
        """Get the schemas directory."""
        return Path(__file__).parent.parent.parent / "src" / "core" / "schemas" / "json"

    def test_limited_access_has_restrictions(self, schema_dir):
        """Test that limited_access_evidence has proper restriction fields."""
        limited_path = schema_dir / "limited_access_evidence.json"

        with open(limited_path) as f:
            limited_schema = json.load(f)

        properties = limited_schema.get("properties", {})

        # Check for key fields
        assert "summary" in properties, "Limited access evidence missing summary"
        assert (
            "access_restrictions" in properties
        ), "Limited access evidence missing access_restrictions"
        assert "evidence_type" in properties, "Limited access evidence missing evidence_type"
        assert "source_id" in properties, "Limited access evidence missing source_id"

        # Check access_restrictions structure
        restrictions = properties["access_restrictions"].get("properties", {})
        assert "reason" in restrictions, "access_restrictions missing reason field"
        assert "access_url" in restrictions, "access_restrictions missing access_url field"
