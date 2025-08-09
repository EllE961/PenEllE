"""Validator for CSL-JSON source schemas."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseValidator, ValidationError, ValidationResult, ValidationSeverity


class SourceValidator(BaseValidator):
    """Validator for CSL-JSON bibliographic sources."""

    # CSL-JSON standard types
    CSL_TYPES = [
        "article",
        "article-journal",
        "article-magazine",
        "article-newspaper",
        "bill",
        "book",
        "broadcast",
        "chapter",
        "dataset",
        "entry",
        "entry-dictionary",
        "entry-encyclopedia",
        "figure",
        "graphic",
        "interview",
        "legal_case",
        "legislation",
        "manuscript",
        "map",
        "motion_picture",
        "musical_score",
        "pamphlet",
        "paper-conference",
        "patent",
        "personal_communication",
        "post",
        "post-weblog",
        "regulation",
        "report",
        "review",
        "review-book",
        "software",
        "song",
        "speech",
        "standard",
        "thesis",
        "treaty",
        "webpage",
    ]

    # Valid identifier types
    IDENTIFIER_TYPES = ["doi", "pmid", "pmcid", "isbn", "issn", "arxiv", "url"]

    def __init__(self, strict_mode: bool = True):
        """Initialize source validator."""
        schema_path = Path(__file__).parent.parent / "json" / "source.json"
        super().__init__(schema_path=schema_path, strict_mode=strict_mode)

    def _custom_validate(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Add custom validation rules for CSL-JSON sources."""
        # Get csl_json data
        if "csl_json" not in data:
            error = ValidationError(
                path="csl_json",
                message="csl_json field is required",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)
            return

        csl_data = data["csl_json"]

        # Validate required CSL fields
        self._validate_csl_required_fields(csl_data, result)

        # Validate type field
        if "type" in csl_data:
            self._validate_source_type(csl_data["type"], result)

        # Validate dates
        self._validate_dates(csl_data, result)

        # Validate authors/contributors
        if "author" in csl_data:
            self._validate_contributors(csl_data["author"], "author", result)
        if "editor" in csl_data:
            self._validate_contributors(csl_data["editor"], "editor", result)

        # Validate identifiers
        self._validate_identifiers(csl_data, result)

        # Validate title and related fields
        self._validate_titles(csl_data, result)

        # Validate publication info
        self._validate_publication_info(csl_data, result)

        # PenEllE-specific validations
        self._validate_penelle_extensions(data, result)

    def _validate_csl_required_fields(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate required CSL-JSON fields."""
        # At minimum, a source should have a type (id is at root level)
        if "type" not in data:
            error = ValidationError(
                path="csl_json.type",
                message="Required field 'type' is missing in csl_json",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

        # Title is effectively required for most types
        if "title" not in data and data.get("type") not in ["personal_communication", "interview"]:
            error = ValidationError(
                path="csl_json.title",
                message="Title is required for this source type",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

    def _validate_source_type(self, source_type: str, result: ValidationResult) -> None:
        """Validate CSL-JSON type field."""
        if source_type not in self.CSL_TYPES:
            error = ValidationError(
                path="csl_json.type",
                message=f"Invalid CSL type '{source_type}'. Must be one of: {', '.join(self.CSL_TYPES)}",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

    def _validate_dates(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate date fields in CSL-JSON format."""
        date_fields = ["issued", "accessed", "submitted", "event-date", "original-date"]

        for field in date_fields:
            if field in data:
                date_data = data[field]
                if isinstance(date_data, dict):
                    self._validate_csl_date(date_data, field, result)
                elif isinstance(date_data, str):
                    # Some sources use string dates
                    try:
                        datetime.fromisoformat(date_data.replace("Z", "+00:00"))
                    except Exception:
                        warning = ValidationError(
                            path=field,
                            message=f"Date string '{date_data}' should be in ISO format or CSL date-parts format",
                            severity=ValidationSeverity.WARNING,
                        )
                        result.add_warning(warning)

    def _validate_csl_date(
        self, date_data: Dict[str, Any], field_name: str, result: ValidationResult
    ) -> None:
        """Validate CSL date-parts structure."""
        if "date-parts" in date_data:
            date_parts = date_data["date-parts"]
            if not isinstance(date_parts, list) or not date_parts:
                error = ValidationError(
                    path=f"{field_name}.date-parts",
                    message="date-parts must be a non-empty list",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)
                return

            # Validate first date array
            if date_parts[0]:
                self._validate_date_array(date_parts[0], f"{field_name}.date-parts[0]", result)

            # If range, validate second date
            if len(date_parts) > 1 and date_parts[1]:
                self._validate_date_array(date_parts[1], f"{field_name}.date-parts[1]", result)

    def _validate_date_array(
        self, date_array: List[int], path: str, result: ValidationResult
    ) -> None:
        """Validate individual date array [year, month, day]."""
        if not isinstance(date_array, list) or len(date_array) == 0 or len(date_array) > 3:
            error = ValidationError(
                path=path,
                message="Date array must have 1-3 elements [year, month, day]",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)
            return

        # Validate year
        if len(date_array) >= 1:
            year = date_array[0]
            if not isinstance(year, int) or year < 1000 or year > 9999:
                error = ValidationError(
                    path=f"{path}[0]",
                    message=f"Invalid year: {year}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate month
        if len(date_array) >= 2:
            month = date_array[1]
            if not isinstance(month, int) or month < 1 or month > 12:
                error = ValidationError(
                    path=f"{path}[1]",
                    message=f"Invalid month: {month}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate day
        if len(date_array) >= 3:
            day = date_array[2]
            if not isinstance(day, int) or day < 1 or day > 31:
                error = ValidationError(
                    path=f"{path}[2]",
                    message=f"Invalid day: {day}",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

    def _validate_contributors(
        self, contributors: Any, contributor_type: str, result: ValidationResult
    ) -> None:
        """Validate author/editor/contributor fields."""
        if not isinstance(contributors, list):
            error = ValidationError(
                path=contributor_type,
                message=f"{contributor_type} must be a list",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)
            return

        for i, contributor in enumerate(contributors):
            path_prefix = f"{contributor_type}[{i}]"

            # Check for name components
            has_family = "family" in contributor
            has_given = "given" in contributor
            has_literal = "literal" in contributor

            if not (has_literal or (has_family or has_given)):
                error = ValidationError(
                    path=path_prefix,
                    message=f"{contributor_type} must have either 'literal' or 'family'/'given' name",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

            # Validate ORCID if present
            if "ORCID" in contributor:
                self._validate_orcid(contributor["ORCID"], f"{path_prefix}.ORCID", result)

    def _validate_orcid(self, orcid: str, path: str, result: ValidationResult) -> None:
        """Validate ORCID identifier format."""
        orcid_pattern = r"^https?://orcid\.org/\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$"
        if not re.match(orcid_pattern, orcid):
            error = ValidationError(
                path=path,
                message=f"Invalid ORCID format: {orcid}",
                severity=ValidationSeverity.ERROR,
            )
            result.add_error(error)

    def _validate_identifiers(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate various identifier fields."""
        # Validate DOI
        if "DOI" in data:
            doi = data["DOI"]
            if not re.match(r"^10\.\d{4,}/[^\s]+$", doi):
                warning = ValidationError(
                    path="DOI",
                    message=f"DOI format may be invalid: {doi}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Validate PMID
        if "PMID" in data:
            pmid = data["PMID"]
            if not (isinstance(pmid, (str, int)) and str(pmid).isdigit()):
                error = ValidationError(
                    path="PMID",
                    message="PMID must be a numeric identifier",
                    severity=ValidationSeverity.ERROR,
                )
                result.add_error(error)

        # Validate ISBN
        if "ISBN" in data:
            isbn = data["ISBN"]
            # Basic ISBN validation (10 or 13 digits)
            isbn_clean = re.sub(r"[^0-9X]", "", str(isbn).upper())
            if len(isbn_clean) not in [10, 13]:
                warning = ValidationError(
                    path="ISBN",
                    message=f"ISBN should be 10 or 13 digits: {isbn}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

    def _validate_titles(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate title and related fields."""
        # Check main title
        if "title" in data:
            title = data["title"]
            if not title or (isinstance(title, str) and not title.strip()):
                error = ValidationError(
                    path="title", message="Title cannot be empty", severity=ValidationSeverity.ERROR
                )
                result.add_error(error)

        # Check container title for articles
        if (
            data.get("type") in ["article", "article-journal", "chapter"]
            and "container-title" not in data
        ):
            warning = ValidationError(
                path="container-title",
                message=f"Source type '{data.get('type')}' should have a container-title",
                severity=ValidationSeverity.WARNING,
            )
            result.add_warning(warning)

    def _validate_publication_info(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate publication-related fields."""
        # For journal articles, check volume/issue
        if data.get("type") == "article-journal":
            if "volume" not in data and "issue" not in data:
                warning = ValidationError(
                    path="volume",
                    message="Journal articles should have volume and/or issue information",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

        # Check page numbers format
        if "page" in data:
            page = data["page"]
            # Valid formats: "123-456", "123", "xi-xv", etc.
            if not re.match(r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)?$", str(page)):
                warning = ValidationError(
                    path="page",
                    message=f"Page format may be invalid: {page}",
                    severity=ValidationSeverity.WARNING,
                )
                result.add_warning(warning)

    def _validate_penelle_extensions(self, data: Dict[str, Any], result: ValidationResult) -> None:
        """Validate PenEllE-specific extensions to CSL-JSON."""
        # Check for PenEllE metadata
        if "_penelle" in data:
            penelle_data = data["_penelle"]

            # Validate confidence score
            if "confidence_score" in penelle_data:
                score = penelle_data["confidence_score"]
                if not isinstance(score, (int, float)) or score < 0 or score > 1:
                    error = ValidationError(
                        path="_penelle.confidence_score",
                        message="confidence_score must be between 0 and 1",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Validate access level
            if "access_level" in penelle_data:
                valid_levels = ["public", "restricted", "private", "confidential"]
                if penelle_data["access_level"] not in valid_levels:
                    error = ValidationError(
                        path="_penelle.access_level",
                        message=f"Invalid access level. Must be one of: {valid_levels}",
                        severity=ValidationSeverity.ERROR,
                    )
                    result.add_error(error)

            # Validate quality indicators
            if "quality_indicators" in penelle_data:
                indicators = penelle_data["quality_indicators"]
                valid_indicators = [
                    "peer-reviewed",
                    "systematic-review",
                    "meta-analysis",
                    "randomized-controlled-trial",
                    "cohort-study",
                    "case-control",
                ]

                if isinstance(indicators, list):
                    for indicator in indicators:
                        if indicator not in valid_indicators:
                            warning = ValidationError(
                                path="_penelle.quality_indicators",
                                message=f"Unknown quality indicator: {indicator}",
                                severity=ValidationSeverity.WARNING,
                            )
                            result.add_warning(warning)
