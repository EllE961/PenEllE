# PenEllE - AI Research Writing Pipeline

PenEllE is an AI-powered research writing pipeline that transforms a thesis statement into a fully-cited, formatted research document. It's designed as a modular, auditable system with strong emphasis on evidence grounding and quality assurance.

## Features

- **Automated Literature Search**: Multi-source literature discovery across academic databases
- **Evidence Extraction**: Typed evidence extraction (statistics, quotes, methods, case studies)
- **Claim Verification**: Every claim is grounded in extracted evidence with provenance tracking
- **Quality Gates**: Automated quality checks for readability, citation density, and similarity
- **Multiple Output Formats**: PDF, DOCX, LaTeX, and Markdown
- **Local LLM Support**: Works with Ollama for complete offline operation

## Architecture

```
INPUT → PLANNING → SOURCING → RETRIEVAL/PARSING → EVIDENCE → DRAFTING → HUMANIZING → FORMATTING → OUTPUT
                         ╲─────────────────── Claim Graph / Fact-Check ─────────────────────╱
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL with pgvector extension
- Redis
- MinIO or S3-compatible storage

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/penelle.git
cd penelle
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up the database:
```bash
alembic upgrade head
```

5. Run the development server:
```bash
uvicorn src.main:app --reload
```

## Project Structure

```
penelle/
├── src/
│   ├── core/           # Core infrastructure (database, storage, auth, config)
│   ├── services/       # Pipeline services (planning, sourcing, drafting, etc.)
│   └── web/           # Web UI and API endpoints
├── tests/             # Test suite
├── config/            # Configuration files
└── docs/              # Documentation
```

## Development

### Running Tests

```bash
pytest
```

### Code Quality

```bash
# Format code
black src tests

# Lint code
ruff check src tests

# Type checking
mypy src
```

### Contributing

1. Follow the commit format: `feat(phase-X): description`
2. Write tests for all new features
3. Ensure all tests pass before submitting PR
4. Maintain >90% code coverage

## Configuration

PenEllE uses YAML configuration files located in the `config/` directory. Key configuration areas include:

- Database connections
- Storage backends
- LLM providers
- Quality gate thresholds
- Connector credentials

## License

[License information to be added]

## Support

For issues and feature requests, please use the GitHub issue tracker.