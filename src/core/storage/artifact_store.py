"""High-level artifact storage interface."""

import gzip
import hashlib
import json
import logging
import mimetypes
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.repositories.artifact import ArtifactRepository
from src.core.storage.s3_client import S3Client, StoragePaths

logger = logging.getLogger(__name__)

# Compression threshold (1MB)
COMPRESSION_THRESHOLD = 1024 * 1024


class ArtifactStore:
    """High-level interface for storing and retrieving pipeline artifacts."""

    def __init__(
        self,
        s3_client: S3Client,
        session: AsyncSession,
        compression_threshold: int = COMPRESSION_THRESHOLD,
    ):
        """Initialize artifact store.

        Args:
            s3_client: S3 client instance
            session: Database session
            compression_threshold: Size threshold for compression
        """
        self.s3_client = s3_client
        self.session = session
        self.artifact_repo = ArtifactRepository(session)
        self.compression_threshold = compression_threshold

    async def save_artifact(
        self,
        run_id: Union[str, UUID],
        stage: str,
        filename: str,
        content: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save a binary artifact.

        Args:
            run_id: Run ID
            stage: Pipeline stage (planning, sourcing, etc.)
            filename: Filename
            content: Binary content
            metadata: Optional metadata

        Returns:
            S3 path to artifact
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        # Calculate checksum
        checksum = hashlib.sha256(content).hexdigest()

        # Determine content type
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Build S3 path
        s3_path = self._build_s3_path(run_id, stage, filename)

        # Upload to S3
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)

        try:
            await self.s3_client.upload_file(
                file_path=tmp_path,
                s3_key=s3_path,
                metadata={
                    "checksum": checksum,
                    "stage": stage,
                    "original_filename": filename,
                    **(metadata or {}),
                },
            )
        finally:
            tmp_path.unlink()

        # Save metadata to database
        await self.artifact_repo.create_or_update(
            run_id=run_id,
            stage=stage,
            filename=filename,
            file_path=s3_path,
            file_size=len(content),
            content_type=content_type,
            checksum=checksum,
            artifact_type="binary",
            compressed=False,
            metadata=metadata,
        )

        logger.info(f"Saved artifact: {s3_path} (size: {len(content)}, checksum: {checksum})")
        return s3_path

    async def get_artifact(self, run_id: Union[str, UUID], stage: str, filename: str) -> bytes:
        """Retrieve a binary artifact.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Filename

        Returns:
            Binary content

        Raises:
            FileNotFoundError: If artifact not found
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        # Get metadata from database
        artifact = await self.artifact_repo.find_by_path(run_id, stage, filename)
        if not artifact:
            raise FileNotFoundError(f"Artifact not found: {stage}/{filename}")

        # Download from S3
        temp_file = Path(f"/tmp/{run_id}_{stage}_{filename}")
        await self.s3_client.download_file(artifact.file_path, temp_file)  # type: ignore[arg-type]

        # Read content
        content = temp_file.read_bytes()
        temp_file.unlink()  # Clean up

        # Decompress if needed
        if artifact.compressed:
            content = gzip.decompress(content)

        # Verify checksum
        actual_checksum = hashlib.sha256(content).hexdigest()
        if actual_checksum != artifact.checksum:
            raise ValueError(f"Checksum mismatch for {stage}/{filename}")

        return content

    async def list_artifacts(
        self, run_id: Union[str, UUID], stage: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List artifacts for a run.

        Args:
            run_id: Run ID
            stage: Optional stage filter

        Returns:
            List of artifact metadata
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        artifacts = await self.artifact_repo.list_by_run(run_id, stage)

        return [
            {
                "id": str(artifact.id),
                "stage": artifact.stage,
                "filename": artifact.filename,
                "type": artifact.artifact_type,
                "size": artifact.file_size,
                "content_type": artifact.content_type,
                "compressed": artifact.compressed,
                "checksum": artifact.checksum,
                "created_at": artifact.created_at.isoformat(),
                "metadata": artifact.artifact_metadata,
            }
            for artifact in artifacts
        ]

    async def save_json_artifact(
        self,
        run_id: Union[str, UUID],
        stage: str,
        filename: str,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save a JSON artifact.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Filename (should end with .json)
            data: Data to serialize as JSON
            metadata: Optional metadata

        Returns:
            S3 path to artifact
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        # Ensure filename ends with .json
        if not filename.endswith(".json"):
            filename += ".json"

        # Serialize to JSON
        json_content = json.dumps(data, indent=2, default=str).encode("utf-8")

        # Calculate checksum
        checksum = hashlib.sha256(json_content).hexdigest()

        # Build S3 path
        s3_path = self._build_s3_path(run_id, stage, filename)

        # Upload directly using S3Client's JSON method
        await self.s3_client.upload_json(
            data=data,
            s3_key=s3_path,
            metadata={
                "checksum": checksum,
                "stage": stage,
                "original_filename": filename,
                **(metadata or {}),
            },
        )

        # Save metadata to database
        await self.artifact_repo.create_or_update(
            run_id=run_id,
            stage=stage,
            filename=filename,
            file_path=s3_path,
            file_size=len(json_content),
            content_type="application/json",
            checksum=checksum,
            artifact_type="json",
            compressed=False,
            metadata=metadata,
        )

        logger.info(f"Saved JSON artifact: {s3_path}")
        return s3_path

    async def get_json_artifact(self, run_id: Union[str, UUID], stage: str, filename: str) -> Any:
        """Retrieve a JSON artifact.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Filename

        Returns:
            Deserialized JSON data

        Raises:
            FileNotFoundError: If artifact not found
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        # Ensure filename ends with .json
        if not filename.endswith(".json"):
            filename += ".json"

        # Get metadata from database
        artifact = await self.artifact_repo.find_by_path(run_id, stage, filename)
        if not artifact:
            raise FileNotFoundError(f"JSON artifact not found: {stage}/{filename}")

        # Download from S3
        data = await self.s3_client.download_json(artifact.file_path)  # type: ignore[arg-type]

        return data

    async def save_text_artifact(
        self,
        run_id: Union[str, UUID],
        stage: str,
        filename: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save a text artifact with optional compression.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Filename
            text: Text content
            metadata: Optional metadata

        Returns:
            S3 path to artifact
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        # Convert to bytes
        content = text.encode("utf-8")
        original_size = len(content)

        # Calculate checksum of original content
        checksum = hashlib.sha256(content).hexdigest()

        # Compress if over threshold
        compressed = False
        if original_size > self.compression_threshold:
            compressed_content = gzip.compress(content, compresslevel=9)
            if len(compressed_content) < original_size:
                content = compressed_content
                compressed = True
                logger.info(
                    f"Compressed {filename}: {original_size} -> {len(content)} bytes "
                    f"({100 * (1 - len(content) / original_size):.1f}% reduction)"
                )

        # Determine content type
        if compressed:
            content_type = "application/gzip"
            display_filename = filename + ".gz"
        else:
            content_type = mimetypes.guess_type(filename)[0] or "text/plain"
            display_filename = filename

        # Build S3 path
        s3_path = self._build_s3_path(run_id, stage, display_filename)

        # Upload to S3
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)

        try:
            await self.s3_client.upload_file(
                file_path=tmp_path,
                s3_key=s3_path,
                metadata={
                    "checksum": checksum,
                    "stage": stage,
                    "original_filename": filename,
                    "original_size": str(original_size),
                    "compressed": str(compressed),
                    **(metadata or {}),
                },
            )
        finally:
            tmp_path.unlink()

        # Save metadata to database
        await self.artifact_repo.create_or_update(
            run_id=run_id,
            stage=stage,
            filename=filename,
            file_path=s3_path,
            file_size=len(content),
            content_type=content_type,
            checksum=checksum,
            artifact_type="text",
            compressed=compressed,
            metadata={"original_size": original_size, **(metadata or {})},
        )

        logger.info(f"Saved text artifact: {s3_path} (compressed: {compressed})")
        return s3_path

    async def get_text_artifact(self, run_id: Union[str, UUID], stage: str, filename: str) -> str:
        """Retrieve a text artifact.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Filename

        Returns:
            Text content

        Raises:
            FileNotFoundError: If artifact not found
        """
        # Get binary content
        content = await self.get_artifact(run_id, stage, filename)

        # Decode to text
        return content.decode("utf-8")

    async def artifact_exists(self, run_id: Union[str, UUID], stage: str, filename: str) -> bool:
        """Check if an artifact exists.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Filename

        Returns:
            True if artifact exists
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        artifact = await self.artifact_repo.find_by_path(run_id, stage, filename)
        if not artifact:
            return False

        # Also verify it exists in S3
        return await self.s3_client.check_object_exists(artifact.file_path)  # type: ignore[arg-type]

    async def copy_artifacts(
        self,
        from_run_id: Union[str, UUID],
        to_run_id: Union[str, UUID],
        stage: Optional[str] = None,
    ) -> int:
        """Copy artifacts between runs.

        Args:
            from_run_id: Source run ID
            to_run_id: Destination run ID
            stage: Optional stage filter

        Returns:
            Number of artifacts copied
        """
        from_run_id = UUID(str(from_run_id)) if isinstance(from_run_id, str) else from_run_id
        to_run_id = UUID(str(to_run_id)) if isinstance(to_run_id, str) else to_run_id

        # Get artifacts to copy
        artifacts = await self.artifact_repo.list_by_run(from_run_id, stage)

        copied = 0
        for artifact in artifacts:
            # Build new S3 path
            new_s3_path = self._build_s3_path(to_run_id, artifact.stage, artifact.filename)  # type: ignore[arg-type]

            # Copy in S3
            await self.s3_client.copy_object(artifact.file_path, new_s3_path)  # type: ignore[arg-type]

            # Create new database record
            await self.artifact_repo.create(
                run_id=to_run_id,
                stage=artifact.stage,
                filename=artifact.filename,
                file_path=new_s3_path,
                file_size=artifact.file_size,
                content_type=artifact.content_type,
                checksum=artifact.checksum,
                artifact_type=artifact.artifact_type,
                compressed=artifact.compressed,
                artifact_metadata=artifact.artifact_metadata,
            )

            copied += 1

        logger.info(f"Copied {copied} artifacts from {from_run_id} to {to_run_id}")
        return copied

    async def delete_run_artifacts(self, run_id: Union[str, UUID]) -> int:
        """Delete all artifacts for a run.

        Args:
            run_id: Run ID

        Returns:
            Number of artifacts deleted
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        # Get all artifacts
        artifacts = await self.artifact_repo.list_by_run(run_id)

        # Delete from S3
        for artifact in artifacts:
            try:
                await self.s3_client.delete_object(artifact.file_path)  # type: ignore[arg-type]
            except Exception as e:
                logger.error(f"Failed to delete S3 object {artifact.file_path}: {e}")

        # Delete from database
        deleted = await self.artifact_repo.delete_by_run(run_id)

        logger.info(f"Deleted {deleted} artifacts for run {run_id}")
        return deleted

    async def get_manifest(self, run_id: Union[str, UUID]) -> Dict[str, Any]:
        """Get manifest of all artifacts for a run.

        Args:
            run_id: Run ID

        Returns:
            Manifest with artifact details and statistics
        """
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        artifacts = await self.artifact_repo.list_by_run(run_id)
        total_size = await self.artifact_repo.get_total_size(run_id)

        # Group by stage
        by_stage: Dict[str, List[Any]] = {}
        for artifact in artifacts:
            stage = str(artifact.stage)  # Convert Column to str
            if stage not in by_stage:
                by_stage[stage] = []

            by_stage[stage].append(
                {
                    "filename": artifact.filename,
                    "type": artifact.artifact_type,
                    "size": artifact.file_size,
                    "compressed": artifact.compressed,
                    "checksum": artifact.checksum,
                    "created_at": artifact.created_at.isoformat(),
                    "metadata": artifact.artifact_metadata,
                }
            )

        return {
            "run_id": str(run_id),
            "total_artifacts": len(artifacts),
            "total_size": total_size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stages": by_stage,
            "summary": {
                stage: {"count": len(items), "total_size": sum(item["size"] for item in items)}
                for stage, items in by_stage.items()
            },
        }

    def _build_s3_path(self, run_id: UUID, stage: str, filename: str) -> str:
        """Build S3 path for an artifact.

        Args:
            run_id: Run ID
            stage: Pipeline stage
            filename: Filename

        Returns:
            S3 path
        """
        # Map stage names to StoragePaths methods
        stage_mapping = {
            "user_library": StoragePaths.user_library,
            "planning": StoragePaths.planning,
            "sourcing": StoragePaths.sourcing,
            "retrieval": StoragePaths.retrieval,
            "evidence": StoragePaths.evidence,
            "drafting": StoragePaths.drafting,
            "humanizing": StoragePaths.humanizing,
            "formatting": StoragePaths.formatting,
            "claim_graph": StoragePaths.claim_graph,
            "quality": StoragePaths.quality,
            "logs": StoragePaths.logs,
        }

        if stage in stage_mapping:
            base_path = stage_mapping[stage](run_id)
        else:
            # Default to generic path
            base_path = f"{StoragePaths.run_base(run_id)}/{stage}"

        return f"{base_path}/{filename}"
