"""Example data for all JSON schemas."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4


def get_example_source() -> Dict[str, Any]:
    """Get example source data that validates against source.json schema."""
    return {
        "schema_version": "1.0",
        "id": str(uuid4()),
        "fingerprint": "a" * 64,  # SHA256 hash
        "csl_json": {
            "type": "article-journal",
            "id": "smith2023climate",
            "title": "Climate Change Impact on Coastal Ecosystems: A Comprehensive Review",
            "author": [
                {"family": "Smith", "given": "John A."},
                {"family": "Johnson", "given": "Emily R."},
                {"family": "Williams", "given": "Michael T."},
            ],
            "issued": {"date-parts": [[2023, 3, 15]]},
            "container-title": "Journal of Environmental Science",
            "volume": "45",
            "issue": "3",
            "page": "234-267",
            "DOI": "10.1234/jes.2023.0145",
            "URL": "https://doi.org/10.1234/jes.2023.0145",
            "abstract": "This comprehensive review examines the multifaceted impacts of climate change on coastal ecosystems worldwide...",
        },
        "quality_score": 0.92,
        "relevance_score": 0.88,
        "connector_name": "openalex",
        "raw_metadata": {
            "openalex_id": "W4321234567",
            "citations_count": 45,
            "open_access": {"is_oa": True, "oa_status": "gold"},
        },
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


def get_example_evidence() -> Dict[str, Any]:
    """Get example evidence data that validates against evidence.json schema."""
    return {
        "schema_version": "1.0",
        "id": str(uuid4()),
        "run_id": str(uuid4()),
        "source_id": str(uuid4()),
        "evidence_type": "statistic",
        "content": "Sea level rise has accelerated to 3.4 mm/year globally, with regional variations ranging from 1-10 mm/year.",
        "context": "Recent satellite altimetry data from 2010-2020 shows accelerating trends in global mean sea level rise, with particularly pronounced increases in the Western Pacific and North Atlantic regions.",
        "page_number": 245,
        "section": "Results and Discussion",
        "confidence_score": 0.95,
        "relevance_score": 0.91,
        "metadata": {
            "extraction_method": "regex_pattern",
            "validation_status": "verified",
            "data_source": "NASA Sea Level Portal",
        },
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


def get_example_claim() -> Dict[str, Any]:
    """Get example claim data that validates against claim.json schema."""
    evidence_ids = [str(uuid4()) for _ in range(3)]
    return {
        "schema_version": "1.0",
        "id": str(uuid4()),
        "run_id": str(uuid4()),
        "claim_text": "Coastal wetlands provide critical ecosystem services that mitigate climate change impacts through carbon sequestration and storm surge protection.",
        "claim_type": "causal",
        "supporting_evidence_ids": evidence_ids,
        "confidence_score": 0.87,
        "verification_status": "verified",
        "section_id": str(uuid4()),
        "position": {"paragraph": 3, "sentence": 2},
        "metadata": {"nli_score": 0.92, "contradicting_evidence_ids": []},
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def get_example_draft_section() -> Dict[str, Any]:
    """Get example draft section data that validates against draft_section.json schema."""
    return {
        "schema_version": "1.0",
        "id": str(uuid4()),
        "run_id": str(uuid4()),
        "section_type": "introduction",
        "title": "Introduction",
        "content": """Climate change represents one of the most pressing environmental challenges of our time, with coastal ecosystems bearing a disproportionate burden of its impacts. These vital ecological zones, where land meets sea, support approximately 40% of the world's population and provide essential ecosystem services valued at trillions of dollars annually.

The accelerating pace of global warming has intensified the vulnerability of coastal regions through multiple interconnected mechanisms. Rising sea levels, increasing ocean temperatures, and changing precipitation patterns collectively threaten the delicate balance of these ecosystems. Recent studies indicate that without significant intervention, up to 70% of coastal wetlands may be lost by 2100.

This comprehensive review synthesizes current understanding of climate change impacts on coastal ecosystems, examining both direct and indirect effects across various temporal and spatial scales. We analyze the latest evidence on ecosystem responses, adaptation mechanisms, and potential mitigation strategies to inform science-based conservation and management decisions.""",
        "order": 1,
        "evidence_ids": [str(uuid4()) for _ in range(5)],
        "claim_ids": [str(uuid4()) for _ in range(3)],
        "word_count": 156,
        "metadata": {
            "generated_by": "claude-3-opus",
            "generation_timestamp": datetime.utcnow().isoformat() + "Z",
            "revision": 2,
        },
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def get_example_run_manifest() -> Dict[str, Any]:
    """Get example run manifest data that validates against run_manifest.json schema."""
    run_id = str(uuid4())
    return {
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
        "created_at": (datetime.utcnow() - timedelta(minutes=21)).isoformat() + "Z",
        "completed_at": datetime.utcnow().isoformat() + "Z",
        # error_message is optional and should be omitted when null
    }


def get_example_run_configuration() -> Dict[str, Any]:
    """Get example run configuration data that validates against run_configuration.json schema."""
    return {
        "schema_version": "1.0",
        "style_pack": "academic_report",
        "target_word_count": 10000,
        "language": "en",
        "source_limits": {
            "max_sources": 150,
            "min_quality_score": 0.6,
            "publication_year_range": {"start": 2015, "end": 2024},
        },
        "connectors": [
            {
                "name": "openalex",
                "enabled": True,
                "priority": 1,
                "config": {"email": "user@example.com", "rate_limit": 100},
            },
            {
                "name": "semantic_scholar",
                "enabled": True,
                "priority": 2,
                "config": {"api_key": "placeholder_key"},
            },
            {"name": "arxiv", "enabled": True, "priority": 3, "config": {}},
        ],
        "quality_gates": {
            "min_evidence_per_claim": 3,
            "min_quality_score": 0.8,
            "max_passive_voice_percentage": 15.0,
            "min_readability_score": 65.0,
        },
        "llm_config": {
            "provider": "ollama",
            "model": "llama3.2:70b",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "output_formats": ["markdown", "pdf", "docx"],
        "advanced": {
            "enable_fact_checking": True,
            "enable_adversarial_search": True,
            "enable_claim_repair": True,
            "chunk_size": 1500,
            "overlap_size": 200,
        },
    }


def get_example_quality_report() -> Dict[str, Any]:
    """Get example quality report data that validates against quality_report.json schema."""
    return {
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
            },
            {
                "severity": "info",
                "category": "evidence",
                "message": "Claim lacks recent supporting evidence (newest source is from 2020)",
                "location": {"section_id": str(uuid4()), "paragraph": 12, "sentence": 1},
                "suggestion": "Consider adding more recent evidence to support this claim",
            },
        ],
        "recommendations": [
            "Reduce average sentence length to improve readability scores",
            "Add more recent sources (2022-2024) to strengthen evidence base",
            "Consider revising passive voice constructions in methodology section",
            "Strengthen evidence for claims in the discussion section",
        ],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def get_example_event_envelope() -> Dict[str, Any]:
    """Get example event envelope data that validates against event_envelope.json schema."""
    return {
        "schema_version": "1.0",
        "event_id": str(uuid4()),
        "run_id": str(uuid4()),
        "event_type": "stage_completed",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "stage": "evidence_extraction",
        "payload": {
            "message": "Evidence extraction completed successfully",
            "progress": {"current": 87, "total": 87, "percentage": 100.0},
            "metrics": {
                "total_evidence_extracted": 342,
                "extraction_duration_seconds": 456.78,
                "average_confidence_score": 0.89,
            },
            "artifacts": [
                {
                    "artifact_id": str(uuid4()),
                    "type": "evidence_batch",
                    "filename": "evidence_final.json",
                }
            ],
        },
        "metadata": {
            "service": "evidence_extractor",
            "version": "1.0.0",
            "hostname": "worker-node-3",
            "correlation_id": str(uuid4()),
        },
    }


def get_example_search_result() -> Dict[str, Any]:
    """Get example search result data that validates against search_result.json schema."""
    return {
        "schema_version": "1.0",
        "connector_name": "semantic_scholar",
        "result_id": "SS:12345678",
        "relevance_score": 0.94,
        "title": "Machine Learning Approaches for Climate Change Prediction in Coastal Regions",
        "authors": [
            {
                "name": "Dr. Sarah Chen",
                "orcid": "0000-0002-1234-5678",
                "affiliation": "MIT Climate Research Center",
            },
            {"name": "Prof. James Martinez", "affiliation": "Stanford University"},
        ],
        "publication_date": "2023-06-15",
        "abstract": "This paper presents novel machine learning approaches for predicting climate change impacts in coastal regions...",
        "identifiers": {"doi": "10.1038/s41558-023-01234-5", "arxiv_id": "2306.12345"},
        "access": {
            "is_open_access": True,
            "pdf_url": "https://arxiv.org/pdf/2306.12345.pdf",
            "html_url": "https://www.nature.com/articles/s41558-023-01234-5",
            "license": "CC-BY-4.0",
        },
        "venue": {
            "name": "Nature Climate Change",
            "type": "journal",
            "volume": "13",
            "issue": "6",
            "pages": "567-578",
        },
        "metrics": {"citation_count": 23, "altmetric_score": 156.4},
        "snippet": "...our results demonstrate that ensemble models combining LSTM networks with physical constraints achieve 15% better accuracy...",
        "metadata": {
            "topics": ["climate change", "machine learning", "coastal science"],
            "field_of_study": ["Environmental Science", "Computer Science"],
        },
    }


def get_example_bibliography() -> Dict[str, Any]:
    """Get example bibliography data that validates against bibliography.json schema."""
    return {
        "schema_version": "1.0",
        "run_id": str(uuid4()),
        "citation_style": "apa",
        "entries": [
            {
                "id": "smith2023climate",
                "source_id": str(uuid4()),
                "formatted_citation": "Smith, J. A., Johnson, E. R., & Williams, M. T. (2023). Climate change impact on coastal ecosystems: A comprehensive review. Journal of Environmental Science, 45(3), 234-267. https://doi.org/10.1234/jes.2023.0145",
                "in_text_citation": "(Smith et al., 2023)",
                "usage_count": 12,
                "sections_used": ["Introduction", "Literature Review", "Discussion"],
                "csl_json": {
                    "type": "article-journal",
                    "title": "Climate change impact on coastal ecosystems: A comprehensive review",
                    "author": [
                        {"family": "Smith", "given": "John A."},
                        {"family": "Johnson", "given": "Emily R."},
                        {"family": "Williams", "given": "Michael T."},
                    ],
                    "issued": {"date-parts": [[2023, 3, 15]]},
                    "container-title": "Journal of Environmental Science",
                    "volume": "45",
                    "issue": "3",
                    "page": "234-267",
                    "DOI": "10.1234/jes.2023.0145",
                },
            },
            {
                "id": "chen2023machine",
                "source_id": str(uuid4()),
                "formatted_citation": "Chen, S., & Martinez, J. (2023). Machine learning approaches for climate change prediction in coastal regions. Nature Climate Change, 13(6), 567-578. https://doi.org/10.1038/s41558-023-01234-5",
                "in_text_citation": "(Chen & Martinez, 2023)",
                "usage_count": 8,
                "sections_used": ["Methodology", "Results"],
                "csl_json": {
                    "type": "article-journal",
                    "title": "Machine learning approaches for climate change prediction in coastal regions",
                    "author": [
                        {"family": "Chen", "given": "Sarah"},
                        {"family": "Martinez", "given": "James"},
                    ],
                    "issued": {"date-parts": [[2023, 6, 15]]},
                    "container-title": "Nature Climate Change",
                    "volume": "13",
                    "issue": "6",
                    "page": "567-578",
                    "DOI": "10.1038/s41558-023-01234-5",
                },
            },
        ],
        "statistics": {
            "total_sources": 87,
            "unique_authors": 234,
            "publication_year_range": {"earliest": 2018, "latest": 2024},
            "source_types": {"article-journal": 65, "book": 8, "report": 10, "thesis": 4},
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def get_example_structured_input() -> Dict[str, Any]:
    """Get example structured input data that validates against structured_input.json schema."""
    return {
        "schema_version": "1.0",
        "thesis": "Analyze the effectiveness of nature-based solutions in mitigating climate change impacts on coastal communities, with a focus on mangrove restoration and living shorelines.",
        "context": "This research is part of a larger project examining sustainable coastal management strategies in Southeast Asia. The target audience includes policymakers, environmental managers, and conservation organizations.",
        "objectives": [
            "Evaluate the carbon sequestration potential of restored mangrove ecosystems",
            "Assess the cost-effectiveness of nature-based solutions compared to traditional infrastructure",
            "Identify best practices for community engagement in restoration projects",
            "Analyze the ecosystem service benefits beyond climate mitigation",
        ],
        "keywords": [
            "nature-based solutions",
            "mangrove restoration",
            "living shorelines",
            "coastal resilience",
            "climate adaptation",
            "ecosystem services",
            "blue carbon",
        ],
        "outline": [
            {
                "section": "Introduction",
                "description": "Background on coastal climate impacts and nature-based solutions",
                "target_word_count": 800,
            },
            {
                "section": "Literature Review",
                "description": "Current state of research on coastal nature-based solutions",
                "target_word_count": 1500,
            },
            {
                "section": "Case Studies",
                "description": "Analysis of successful mangrove restoration projects",
                "target_word_count": 2000,
            },
            {
                "section": "Economic Analysis",
                "description": "Cost-benefit comparison with traditional approaches",
                "target_word_count": 1200,
            },
            {
                "section": "Recommendations",
                "description": "Best practices and policy recommendations",
                "target_word_count": 1000,
            },
        ],
        "constraints": {
            "required_sources": [
                "10.1038/s41558-022-01584-2",  # Key paper on mangrove carbon
                "10.1126/science.abm8082",  # Living shorelines review
            ],
            "excluded_sources": ["10.1234/predatory-journal-123"],  # Known predatory journal
            "methodology_requirements": [
                "Include quantitative cost-benefit analysis",
                "Use IPCC guidelines for carbon accounting",
                "Apply ecosystem service valuation frameworks",
            ],
        },
        "user_library": {
            "enabled": True,
            "collection_ids": [
                str(uuid4()),  # "Coastal Management" collection
                str(uuid4()),  # "Climate Solutions" collection
            ],
        },
        "preferences": {
            "citation_style": "apa",
            "language_variant": "en-US",
            "formality_level": "formal",
        },
    }


def get_example_limited_access_evidence() -> Dict[str, Any]:
    """Get example limited access evidence data that validates against limited_access_evidence.json schema."""
    return {
        "schema_version": "1.0",
        "id": str(uuid4()),
        "source_id": str(uuid4()),
        "evidence_type": "figure",
        "summary": "Satellite imagery analysis showing 35% reduction in mangrove coverage along the Mekong Delta between 2000-2020, with accelerated loss rates after 2015 corresponding to increased aquaculture development.",
        "access_restrictions": {
            "reason": "copyright",
            "access_url": "https://www.sciencedirect.com/science/article/pii/S0034425723001234",
            "license": "Elsevier Copyright",
            # embargo_until is optional and should be omitted when null
        },
        "metadata": {
            "page_number": 8,
            "section": "Results",
            "confidence_score": 0.95,
            "figure_caption": "Figure 3: Landsat-derived mangrove extent changes in the Mekong Delta",
            "data_type": "remote_sensing",
        },
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


def save_all_examples() -> None:
    """Save all example data to JSON files."""
    examples_dir = Path(__file__).parent

    examples = {
        "source": get_example_source(),
        "evidence": get_example_evidence(),
        "claim": get_example_claim(),
        "draft_section": get_example_draft_section(),
        "run_manifest": get_example_run_manifest(),
        "run_configuration": get_example_run_configuration(),
        "quality_report": get_example_quality_report(),
        "event_envelope": get_example_event_envelope(),
        "search_result": get_example_search_result(),
        "bibliography": get_example_bibliography(),
        "structured_input": get_example_structured_input(),
        "limited_access_evidence": get_example_limited_access_evidence(),
    }

    for name, data in examples.items():
        file_path = examples_dir / f"{name}_example.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved {name} example to {file_path}")


if __name__ == "__main__":
    save_all_examples()
