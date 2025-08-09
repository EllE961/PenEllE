"""Tests for the artifact store."""

import gzip
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models import Artifact
from src.core.storage.artifact_store import ArtifactStore
from src.core.storage.s3_client import S3Client


@pytest.fixture()
def mock_s3_client():
    """Create a mock S3 client."""
    client = MagicMock(spec=S3Client)
    # Make all methods async mocks
    client.upload_file = AsyncMock()
    client.download_file = AsyncMock()
    client.upload_json = AsyncMock()
    client.download_json = AsyncMock()
    client.check_object_exists = AsyncMock(return_value=True)
    client.copy_object = AsyncMock()
    client.delete_object = AsyncMock()
    return client


@pytest.fixture()
def mock_session():
    """Create a mock database session."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture()
def mock_artifact_repo():
    """Create a mock artifact repository."""
    with patch("src.core.storage.artifact_store.ArtifactRepository") as mock_repo_class:
        repo = MagicMock()
        repo.create_or_update = AsyncMock()
        repo.find_by_path = AsyncMock()
        repo.list_by_run = AsyncMock()
        repo.delete_by_run = AsyncMock()
        repo.get_total_size = AsyncMock()
        repo.create = AsyncMock()
        mock_repo_class.return_value = repo
        yield repo


@pytest.fixture()
def artifact_store(mock_s3_client, mock_session, mock_artifact_repo):
    """Create an artifact store instance."""
    return ArtifactStore(mock_s3_client, mock_session)


class TestArtifactStore:
    """Test artifact store functionality."""

    @pytest.mark.asyncio()
    async def test_save_artifact(self, artifact_store, mock_s3_client, mock_artifact_repo):
        """Test saving a binary artifact."""
        run_id = uuid4()
        stage = "planning"
        filename = "test.pdf"
        content = b"PDF content here"
        metadata = {"author": "test"}

        # Mock the repository to return a created artifact
        mock_artifact = MagicMock(spec=Artifact)
        mock_artifact_repo.create_or_update.return_value = mock_artifact

        # Save artifact
        _ = await artifact_store.save_artifact(
            run_id=run_id, stage=stage, filename=filename, content=content, metadata=metadata
        )

        # Verify S3 upload
        mock_s3_client.upload_file.assert_called_once()
        call_args = mock_s3_client.upload_file.call_args
        assert call_args.kwargs["s3_key"] == f"runs/{run_id}/01_planning/{filename}"
        assert "metadata" in call_args.kwargs
        assert call_args.kwargs["metadata"]["stage"] == stage
        assert call_args.kwargs["metadata"]["author"] == "test"

        # Verify database save
        mock_artifact_repo.create_or_update.assert_called_once()
        db_call_args = mock_artifact_repo.create_or_update.call_args
        assert db_call_args.kwargs["run_id"] == run_id
        assert db_call_args.kwargs["stage"] == stage
        assert db_call_args.kwargs["filename"] == filename
        assert db_call_args.kwargs["file_size"] == len(content)
        assert db_call_args.kwargs["content_type"] == "application/pdf"
        assert db_call_args.kwargs["artifact_type"] == "binary"
        assert db_call_args.kwargs["compressed"] is False

    @pytest.mark.asyncio()
    async def test_get_artifact(self, artifact_store, mock_s3_client, mock_artifact_repo):
        """Test retrieving a binary artifact."""
        run_id = uuid4()
        stage = "evidence"
        filename = "data.bin"
        content = b"Binary data"
        checksum = "abc123"

        # Mock artifact in database
        mock_artifact = MagicMock(spec=Artifact)
        mock_artifact.file_path = f"runs/{run_id}/04_evidence/{filename}"
        mock_artifact.compressed = False
        mock_artifact.checksum = checksum
        mock_artifact_repo.find_by_path.return_value = mock_artifact

        # Mock S3 download
        async def mock_download(s3_key, local_path):
            local_path.write_bytes(content)

        mock_s3_client.download_file.side_effect = mock_download

        # Mock checksum calculation
        with patch("hashlib.sha256") as mock_hash:
            mock_hash.return_value.hexdigest.return_value = checksum

            # Get artifact
            result = await artifact_store.get_artifact(run_id, stage, filename)

            assert result == content
            mock_artifact_repo.find_by_path.assert_called_once_with(run_id, stage, filename)
            mock_s3_client.download_file.assert_called_once()

    @pytest.mark.asyncio()
    async def test_get_artifact_not_found(self, artifact_store, mock_artifact_repo):
        """Test retrieving non-existent artifact."""
        run_id = uuid4()
        stage = "planning"
        filename = "missing.txt"

        # Mock artifact not found
        mock_artifact_repo.find_by_path.return_value = None

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError, match="Artifact not found"):
            await artifact_store.get_artifact(run_id, stage, filename)

    @pytest.mark.asyncio()
    async def test_save_json_artifact(self, artifact_store, mock_s3_client, mock_artifact_repo):
        """Test saving a JSON artifact."""
        run_id = uuid4()
        stage = "planning"
        filename = "plan"  # Should auto-add .json
        data = {"thesis": "Test thesis", "sections": ["intro", "body", "conclusion"]}

        # Save JSON artifact
        _ = await artifact_store.save_json_artifact(
            run_id=run_id, stage=stage, filename=filename, data=data
        )

        # Verify S3 upload
        mock_s3_client.upload_json.assert_called_once()
        call_args = mock_s3_client.upload_json.call_args
        assert call_args.kwargs["data"] == data
        assert call_args.kwargs["s3_key"] == f"runs/{run_id}/01_planning/plan.json"

        # Verify database save
        mock_artifact_repo.create_or_update.assert_called_once()
        db_call_args = mock_artifact_repo.create_or_update.call_args
        assert db_call_args.kwargs["filename"] == "plan.json"
        assert db_call_args.kwargs["content_type"] == "application/json"
        assert db_call_args.kwargs["artifact_type"] == "json"

    @pytest.mark.asyncio()
    async def test_get_json_artifact(self, artifact_store, mock_s3_client, mock_artifact_repo):
        """Test retrieving a JSON artifact."""
        run_id = uuid4()
        stage = "sourcing"
        filename = "sources.json"
        data = {"sources": ["source1", "source2"]}

        # Mock artifact in database
        mock_artifact = MagicMock(spec=Artifact)
        mock_artifact.file_path = f"runs/{run_id}/02_sourcing/{filename}"
        mock_artifact_repo.find_by_path.return_value = mock_artifact

        # Mock S3 download
        mock_s3_client.download_json.return_value = data

        # Get JSON artifact
        result = await artifact_store.get_json_artifact(run_id, stage, filename)

        assert result == data
        mock_s3_client.download_json.assert_called_once_with(mock_artifact.file_path)

    @pytest.mark.asyncio()
    async def test_save_text_artifact_small(
        self, artifact_store, mock_s3_client, mock_artifact_repo
    ):
        """Test saving a small text artifact (no compression)."""
        run_id = uuid4()
        stage = "drafting"
        filename = "section1.txt"
        text = "This is a small text file."

        # Set compression threshold high so this won't compress
        artifact_store.compression_threshold = 1024 * 1024

        # Save text artifact
        _ = await artifact_store.save_text_artifact(
            run_id=run_id, stage=stage, filename=filename, text=text
        )

        # Verify S3 upload (not compressed)
        mock_s3_client.upload_file.assert_called_once()
        call_args = mock_s3_client.upload_file.call_args

        # Read the temporary file content
        tmp_path = call_args.kwargs["file_path"]
        assert isinstance(tmp_path, Path)

        # Verify database save
        mock_artifact_repo.create_or_update.assert_called_once()
        db_call_args = mock_artifact_repo.create_or_update.call_args
        assert db_call_args.kwargs["compressed"] is False
        assert db_call_args.kwargs["content_type"] == "text/plain"

    @pytest.mark.asyncio()
    async def test_save_text_artifact_large_compressed(
        self, artifact_store, mock_s3_client, mock_artifact_repo
    ):
        """Test saving a large text artifact with compression."""
        run_id = uuid4()
        stage = "drafting"
        filename = "large_section.txt"
        # Create text larger than 1KB
        text = "This is a large text file. " * 100

        # Set low compression threshold
        artifact_store.compression_threshold = 100

        # Save text artifact
        _ = await artifact_store.save_text_artifact(
            run_id=run_id, stage=stage, filename=filename, text=text
        )

        # Verify S3 upload (compressed)
        mock_s3_client.upload_file.assert_called_once()
        call_args = mock_s3_client.upload_file.call_args
        assert call_args.kwargs["s3_key"].endswith(".txt.gz")

        # Verify database save
        mock_artifact_repo.create_or_update.assert_called_once()
        db_call_args = mock_artifact_repo.create_or_update.call_args
        assert db_call_args.kwargs["compressed"] is True
        assert db_call_args.kwargs["content_type"] == "application/gzip"
        assert db_call_args.kwargs["metadata"]["original_size"] == len(text.encode("utf-8"))

    @pytest.mark.asyncio()
    async def test_get_text_artifact_compressed(
        self, artifact_store, mock_s3_client, mock_artifact_repo
    ):
        """Test retrieving a compressed text artifact."""
        run_id = uuid4()
        stage = "humanizing"
        filename = "improved.txt"
        original_text = "This is the original text content."
        compressed_content = gzip.compress(original_text.encode("utf-8"))

        # Mock artifact in database (compressed)
        mock_artifact = MagicMock(spec=Artifact)
        mock_artifact.file_path = f"runs/{run_id}/06_humanizing/{filename}.gz"
        mock_artifact.compressed = True
        mock_artifact.checksum = "def456"
        mock_artifact_repo.find_by_path.return_value = mock_artifact

        # Mock S3 download
        async def mock_download(s3_key, local_path):
            local_path.write_bytes(compressed_content)

        mock_s3_client.download_file.side_effect = mock_download

        # Mock checksum validation
        with patch("hashlib.sha256") as mock_hash:
            mock_hash.return_value.hexdigest.return_value = "def456"

            # Get text artifact
            result = await artifact_store.get_text_artifact(run_id, stage, filename)

            assert result == original_text

    @pytest.mark.asyncio()
    async def test_artifact_exists(self, artifact_store, mock_s3_client, mock_artifact_repo):
        """Test checking if artifact exists."""
        run_id = uuid4()
        stage = "quality"
        filename = "report.json"

        # Mock artifact exists in database
        mock_artifact = MagicMock(spec=Artifact)
        mock_artifact.file_path = f"runs/{run_id}/quality/{filename}"
        mock_artifact_repo.find_by_path.return_value = mock_artifact

        # Mock S3 object exists
        mock_s3_client.check_object_exists.return_value = True

        # Check existence
        exists = await artifact_store.artifact_exists(run_id, stage, filename)

        assert exists is True
        mock_artifact_repo.find_by_path.assert_called_once_with(run_id, stage, filename)
        mock_s3_client.check_object_exists.assert_called_once_with(mock_artifact.file_path)

    @pytest.mark.asyncio()
    async def test_list_artifacts(self, artifact_store, mock_artifact_repo):
        """Test listing artifacts for a run."""
        run_id = uuid4()

        # Mock artifacts
        artifacts = [
            MagicMock(
                id=uuid4(),
                stage="planning",
                filename="plan.json",
                artifact_type="json",
                file_size=1024,
                content_type="application/json",
                compressed=False,
                checksum="abc123",
                created_at=MagicMock(isoformat=lambda: "2023-01-01T00:00:00"),
                artifact_metadata={"version": 1},
            ),
            MagicMock(
                id=uuid4(),
                stage="sourcing",
                filename="sources.json",
                artifact_type="json",
                file_size=2048,
                content_type="application/json",
                compressed=False,
                checksum="def456",
                created_at=MagicMock(isoformat=lambda: "2023-01-01T01:00:00"),
                artifact_metadata=None,
            ),
        ]
        mock_artifact_repo.list_by_run.return_value = artifacts

        # List artifacts
        result = await artifact_store.list_artifacts(run_id)

        assert len(result) == 2
        assert result[0]["stage"] == "planning"
        assert result[0]["filename"] == "plan.json"
        assert result[0]["size"] == 1024
        assert result[1]["stage"] == "sourcing"

    @pytest.mark.asyncio()
    async def test_copy_artifacts(self, artifact_store, mock_s3_client, mock_artifact_repo):
        """Test copying artifacts between runs."""
        from_run_id = uuid4()
        to_run_id = uuid4()

        # Mock source artifacts
        artifacts = [
            MagicMock(
                stage="planning",
                filename="plan.json",
                file_path=f"runs/{from_run_id}/01_planning/plan.json",
                file_size=1024,
                content_type="application/json",
                checksum="abc123",
                artifact_type="json",
                compressed=False,
                artifact_metadata={},
            ),
            MagicMock(
                stage="sourcing",
                filename="sources.json",
                file_path=f"runs/{from_run_id}/02_sourcing/sources.json",
                file_size=2048,
                content_type="application/json",
                checksum="def456",
                artifact_type="json",
                compressed=False,
                artifact_metadata={},
            ),
        ]
        mock_artifact_repo.list_by_run.return_value = artifacts

        # Copy artifacts
        count = await artifact_store.copy_artifacts(from_run_id, to_run_id)

        assert count == 2

        # Verify S3 copies
        assert mock_s3_client.copy_object.call_count == 2

        # Verify database creates
        assert mock_artifact_repo.create.call_count == 2

    @pytest.mark.asyncio()
    async def test_delete_run_artifacts(self, artifact_store, mock_s3_client, mock_artifact_repo):
        """Test deleting all artifacts for a run."""
        run_id = uuid4()

        # Mock artifacts to delete
        artifacts = [
            MagicMock(file_path=f"runs/{run_id}/01_planning/plan.json"),
            MagicMock(file_path=f"runs/{run_id}/02_sourcing/sources.json"),
        ]
        mock_artifact_repo.list_by_run.return_value = artifacts
        mock_artifact_repo.delete_by_run.return_value = 2

        # Delete artifacts
        count = await artifact_store.delete_run_artifacts(run_id)

        assert count == 2

        # Verify S3 deletes
        assert mock_s3_client.delete_object.call_count == 2

        # Verify database delete
        mock_artifact_repo.delete_by_run.assert_called_once_with(run_id)

    @pytest.mark.asyncio()
    async def test_get_manifest(self, artifact_store, mock_artifact_repo):
        """Test getting artifact manifest."""
        run_id = uuid4()

        # Mock artifacts
        artifacts = [
            MagicMock(
                stage="planning",
                filename="plan.json",
                artifact_type="json",
                file_size=1024,
                compressed=False,
                checksum="abc123",
                created_at=MagicMock(isoformat=lambda: "2023-01-01T00:00:00"),
                artifact_metadata={"version": 1},
            ),
            MagicMock(
                stage="planning",
                filename="outline.txt",
                artifact_type="text",
                file_size=512,
                compressed=False,
                checksum="xyz789",
                created_at=MagicMock(isoformat=lambda: "2023-01-01T00:30:00"),
                artifact_metadata=None,
            ),
            MagicMock(
                stage="sourcing",
                filename="sources.json",
                artifact_type="json",
                file_size=2048,
                compressed=False,
                checksum="def456",
                created_at=MagicMock(isoformat=lambda: "2023-01-01T01:00:00"),
                artifact_metadata=None,
            ),
        ]
        mock_artifact_repo.list_by_run.return_value = artifacts
        mock_artifact_repo.get_total_size.return_value = 3584

        # Get manifest
        manifest = await artifact_store.get_manifest(run_id)

        assert manifest["run_id"] == str(run_id)
        assert manifest["total_artifacts"] == 3
        assert manifest["total_size"] == 3584
        assert "generated_at" in manifest

        # Check stages
        assert "planning" in manifest["stages"]
        assert len(manifest["stages"]["planning"]) == 2
        assert "sourcing" in manifest["stages"]
        assert len(manifest["stages"]["sourcing"]) == 1

        # Check summary
        assert manifest["summary"]["planning"]["count"] == 2
        assert manifest["summary"]["planning"]["total_size"] == 1536
        assert manifest["summary"]["sourcing"]["count"] == 1
        assert manifest["summary"]["sourcing"]["total_size"] == 2048


@pytest.mark.asyncio()
class TestArtifactStoreCompression:
    """Test compression functionality."""

    async def test_compression_reduces_size(self):
        """Test that compression actually reduces file size for compressible content."""
        # Create highly compressible content
        text = "a" * 10000  # 10KB of 'a' characters
        original_bytes = text.encode("utf-8")
        compressed_bytes = gzip.compress(original_bytes, compresslevel=9)

        # Verify compression works
        assert len(compressed_bytes) < len(original_bytes)
        assert len(compressed_bytes) < 100  # Should compress to tiny size

        # Verify decompression
        decompressed = gzip.decompress(compressed_bytes)
        assert decompressed == original_bytes

    async def test_compression_threshold(self):
        """Test compression threshold behavior."""
        # Small text (should not compress)
        small_text = "Small text"
        small_bytes = small_text.encode("utf-8")

        # Large text (should compress)
        large_text = "Large text content " * 1000
        large_bytes = large_text.encode("utf-8")

        threshold = 1024  # 1KB

        assert len(small_bytes) < threshold
        assert len(large_bytes) > threshold
