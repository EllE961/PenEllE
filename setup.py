#!/usr/bin/env python
"""Setup script for PenEllE."""

from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open("requirements.txt") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Define optional dependencies
extras_require = {
    "dev": [
        "pytest>=7.4.0",
        "pytest-asyncio>=0.21.0",
        "pytest-cov>=4.1.0",
        "pytest-mock>=3.12.0",
        "pytest-xdist>=3.8.0",
        "pytest-timeout>=2.4.0",
        "pytest-benchmark>=5.1.0",
        "black>=23.11.0",
        "ruff>=0.1.6",
        "mypy>=1.7.0",
        "pre-commit>=3.5.0",
    ],
    "llm": [
        "ollama>=0.1.7",
        "openai>=1.3.0",
        "anthropic>=0.7.0",
        "transformers>=4.35.0",
    ],
    "docs": [
        "sphinx>=7.2.0",
        "sphinx-rtd-theme>=2.0.0",
        "sphinx-autodoc-typehints>=1.25.0",
        "myst-parser>=2.0.0",
    ],
}

setup(
    packages=find_packages(where=".", include=["src", "src.*"]),
    package_dir={"": "."},
    install_requires=requirements,
    extras_require=extras_require,
)