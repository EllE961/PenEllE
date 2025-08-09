"""Storage module for PenEllE."""

from enum import Enum
from typing import Any, Dict, Optional

from .artifact_store import ArtifactStore
from .file_manager import FileManager, FileProcessor
from .s3_client import S3Client, StoragePaths


class ArtifactType(str, Enum):
    """Types of artifacts that can be stored."""

    INPUT = "input"
    OUTPUT = "output"
    INTERMEDIATE = "intermediate"
    FINAL = "final"


class SimpleArtifactStore:
    """Simple in-memory artifact store for development."""

    def __init__(self):
        """Initialize simple artifact store."""
        self.artifacts: Dict[str, Dict[str, Any]] = {}

    async def store(
        self,
        run_id: str,
        stage: str,
        artifact_type: ArtifactType,
        data: Any,
        key: str = "artifact",
    ) -> None:
        """Store artifact in memory.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            artifact_type: Type of artifact
            data: Data to store
            key: Artifact key
        """
        artifact_key = f"{run_id}:{stage}:{key}"
        self.artifacts[artifact_key] = {
            "data": data,
            "type": artifact_type,
            "stage": stage,
            "run_id": run_id,
        }

    async def get(self, run_id: str, key: str) -> Optional[Dict[str, Any]]:
        """Get artifact by key.

        Args:
            run_id: Run ID
            key: Artifact key

        Returns:
            Artifact data or None
        """
        # Try different stages
        stages = ["planning", "sourcing", "drafting", "review", "editing"]

        for stage in stages:
            artifact_key = f"{run_id}:{stage}:{key}"
            if artifact_key in self.artifacts:
                return self.artifacts[artifact_key]["data"]

        return None


# Dependency provider for FastAPI
_artifact_store = None


async def get_artifact_store() -> SimpleArtifactStore:
    """Get artifact store instance for dependency injection.

    Returns:
        SimpleArtifactStore instance
    """
    global _artifact_store

    if _artifact_store is None:
        _artifact_store = SimpleArtifactStore()

    return _artifact_store


__all__ = [
    "S3Client",
    "StoragePaths",
    "ArtifactStore",
    "ArtifactType",
    "FileManager",
    "FileProcessor",
    "SimpleArtifactStore",
    "get_artifact_store",
]
