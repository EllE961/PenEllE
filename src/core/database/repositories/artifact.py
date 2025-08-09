"""Repository for artifact operations."""

import hashlib
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models import Artifact
from src.core.database.repositories.base import BaseRepository


class ArtifactRepository(BaseRepository[Artifact]):
    """Repository for artifact database operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository."""
        super().__init__(Artifact, session)

    async def find_by_path(self, run_id: UUID, stage: str, filename: str) -> Optional[Artifact]:
        """Find artifact by run, stage, and filename.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Artifact filename

        Returns:
            Artifact if found, None otherwise
        """
        stmt = select(Artifact).where(
            and_(Artifact.run_id == run_id, Artifact.stage == stage, Artifact.filename == filename)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_run(
        self, run_id: UUID, stage: Optional[str] = None, artifact_type: Optional[str] = None
    ) -> List[Artifact]:
        """List artifacts for a run.

        Args:
            run_id: Run ID
            stage: Optional stage filter
            artifact_type: Optional type filter

        Returns:
            List of artifacts
        """
        stmt = select(Artifact).where(Artifact.run_id == run_id)

        if stage:
            stmt = stmt.where(Artifact.stage == stage)
        if artifact_type:
            stmt = stmt.where(Artifact.artifact_type == artifact_type)

        stmt = stmt.order_by(Artifact.created_at)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_or_update(
        self,
        run_id: UUID,
        stage: str,
        filename: str,
        file_path: str,
        file_size: int,
        content_type: str,
        checksum: str,
        artifact_type: str = "binary",
        compressed: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Artifact:
        """Create or update an artifact record.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Artifact filename
            file_path: S3 path
            file_size: File size in bytes
            content_type: MIME type
            checksum: SHA256 checksum
            artifact_type: Type (json, text, binary)
            compressed: Whether file is compressed
            metadata: Additional metadata

        Returns:
            Created or updated artifact
        """
        # Try to find existing artifact
        existing = await self.find_by_path(run_id, stage, filename)

        if existing:
            # Update existing artifact
            updated = await self.update(
                id=existing.id,  # type: ignore[arg-type]
                file_path=file_path,
                file_size=file_size,
                content_type=content_type,
                checksum=checksum,
                artifact_type=artifact_type,
                compressed=compressed,
                artifact_metadata=metadata,
            )
            if updated:
                return updated
            else:
                # This shouldn't happen, but handle it
                return existing
        else:
            # Create new artifact
            return await self.create(
                run_id=run_id,
                stage=stage,
                filename=filename,
                file_path=file_path,
                file_size=file_size,
                content_type=content_type,
                checksum=checksum,
                artifact_type=artifact_type,
                compressed=compressed,
                artifact_metadata=metadata,
            )

    async def delete_by_run(self, run_id: UUID) -> int:
        """Delete all artifacts for a run.

        Args:
            run_id: Run ID

        Returns:
            Number of deleted artifacts
        """
        stmt = delete(Artifact).where(Artifact.run_id == run_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_total_size(self, run_id: UUID) -> int:
        """Get total size of artifacts for a run.

        Args:
            run_id: Run ID

        Returns:
            Total size in bytes
        """
        from sqlalchemy import func

        stmt = select(func.sum(Artifact.file_size)).where(Artifact.run_id == run_id)
        result = await self.session.execute(stmt)
        total = result.scalar_one_or_none()
        return total or 0

    @staticmethod
    def calculate_checksum(data: bytes) -> str:
        """Calculate SHA256 checksum.

        Args:
            data: Data to checksum

        Returns:
            Hex digest of checksum
        """
        return hashlib.sha256(data).hexdigest()
