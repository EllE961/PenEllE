"""Tests for S3/MinIO client."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from src.core.storage.s3_client import S3Client, StoragePaths


class TestStoragePaths:
    """Test storage path utilities."""

    def test_run_base(self):
        """Test run base path generation."""
        run_id = uuid4()
        assert StoragePaths.run_base(run_id) == f"runs/{run_id}"
        assert StoragePaths.run_base(str(run_id)) == f"runs/{run_id}"

    def test_all_paths(self):
        """Test all path generation methods."""
        run_id = uuid4()

        assert StoragePaths.user_library(run_id) == f"runs/{run_id}/00_user_library"
        assert StoragePaths.planning(run_id) == f"runs/{run_id}/01_planning"
        assert StoragePaths.sourcing(run_id) == f"runs/{run_id}/02_sourcing"
        assert StoragePaths.retrieval(run_id) == f"runs/{run_id}/03_retrieval"
        assert StoragePaths.evidence(run_id) == f"runs/{run_id}/04_evidence"
        assert StoragePaths.drafting(run_id) == f"runs/{run_id}/05_drafting"
        assert StoragePaths.humanizing(run_id) == f"runs/{run_id}/06_humanizing"
        assert StoragePaths.formatting(run_id) == f"runs/{run_id}/07_formatting"
        assert StoragePaths.claim_graph(run_id) == f"runs/{run_id}/claim_graph"
        assert StoragePaths.quality(run_id) == f"runs/{run_id}/quality"
        assert StoragePaths.logs(run_id) == f"runs/{run_id}/logs"


@pytest.fixture()
def mock_s3_client():
    """Create a mock S3 client."""
    with patch("src.core.storage.s3_client.aioboto3.Session") as mock_session:
        # Create mock client
        mock_client = AsyncMock()

        # Configure session to return mock client
        mock_session.return_value.client.return_value.__aenter__.return_value = mock_client

        # Create S3Client instance
        client = S3Client()
        # Manually set the _client without entering context
        client._client = mock_client
        client._stack = AsyncMock()

        return client


class TestS3Client:
    """Test S3Client functionality."""

    @pytest.mark.asyncio()
    async def test_create_bucket_if_not_exists_already_exists(self, mock_s3_client):
        """Test creating bucket when it already exists."""
        # Bucket already exists
        mock_s3_client._client.head_bucket.return_value = {"ResponseMetadata": {}}

        result = await mock_s3_client.create_bucket_if_not_exists()
        assert result is False
        mock_s3_client._client.head_bucket.assert_called_once_with(
            Bucket=mock_s3_client.bucket_name
        )

    @pytest.mark.asyncio()
    async def test_create_bucket_if_not_exists_creates_new(self, mock_s3_client):
        """Test creating bucket when it doesn't exist."""
        # Bucket doesn't exist
        mock_s3_client._client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "HeadBucket"
        )
        mock_s3_client._client.create_bucket.return_value = {"ResponseMetadata": {}}

        result = await mock_s3_client.create_bucket_if_not_exists()
        assert result is True
        mock_s3_client._client.create_bucket.assert_called_once()

    @pytest.mark.asyncio()
    async def test_upload_json(self, mock_s3_client):
        """Test uploading JSON data."""
        data = {"test": "data", "number": 42}
        s3_key = "test/data.json"

        result = await mock_s3_client.upload_json(data, s3_key)

        assert result == s3_key
        mock_s3_client._client.put_object.assert_called_once()
        call_args = mock_s3_client._client.put_object.call_args

        # Verify JSON data
        uploaded_data = json.loads(call_args.kwargs["Body"].decode("utf-8"))
        assert uploaded_data == data
        assert call_args.kwargs["Key"] == s3_key
        assert call_args.kwargs["ContentType"] == "application/json"

    @pytest.mark.asyncio()
    async def test_download_json(self, mock_s3_client):
        """Test downloading JSON data."""
        data = {"test": "data", "number": 42}
        s3_key = "test/data.json"

        # Mock response
        mock_body = AsyncMock()
        mock_body.read.return_value = json.dumps(data).encode("utf-8")
        mock_s3_client._client.get_object.return_value = {"Body": mock_body}

        result = await mock_s3_client.download_json(s3_key)

        assert result == data
        mock_s3_client._client.get_object.assert_called_once_with(
            Bucket=mock_s3_client.bucket_name, Key=s3_key
        )

    @pytest.mark.asyncio()
    async def test_list_objects(self, mock_s3_client):
        """Test listing objects."""
        prefix = "runs/test-run/"

        # Mock response
        mock_s3_client._client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "runs/test-run/file1.txt",
                    "Size": 1024,
                    "LastModified": "2023-01-01T00:00:00Z",
                    "ETag": '"abc123"',
                },
                {
                    "Key": "runs/test-run/file2.json",
                    "Size": 2048,
                    "LastModified": "2023-01-02T00:00:00Z",
                    "ETag": '"def456"',
                },
            ],
            "IsTruncated": False,
        }

        result = await mock_s3_client.list_objects(prefix=prefix)

        assert len(result) == 2
        assert result[0]["key"] == "runs/test-run/file1.txt"
        assert result[0]["size"] == 1024
        assert result[0]["etag"] == "abc123"

        mock_s3_client._client.list_objects_v2.assert_called_once_with(
            Bucket=mock_s3_client.bucket_name, MaxKeys=1000, Prefix=prefix
        )

    @pytest.mark.asyncio()
    async def test_delete_object(self, mock_s3_client):
        """Test deleting an object."""
        s3_key = "test/file.txt"

        result = await mock_s3_client.delete_object(s3_key)

        assert result is True
        mock_s3_client._client.delete_object.assert_called_once_with(
            Bucket=mock_s3_client.bucket_name, Key=s3_key
        )

    @pytest.mark.asyncio()
    async def test_generate_presigned_url(self, mock_s3_client):
        """Test generating presigned URL."""
        s3_key = "test/file.txt"
        expected_url = "https://example.com/presigned-url"

        mock_s3_client._client.generate_presigned_url.return_value = expected_url

        result = await mock_s3_client.generate_presigned_url(s3_key)

        assert result == expected_url
        mock_s3_client._client.generate_presigned_url.assert_called_once()

    @pytest.mark.asyncio()
    async def test_check_object_exists_true(self, mock_s3_client):
        """Test checking if object exists (exists case)."""
        s3_key = "test/file.txt"

        mock_s3_client._client.head_object.return_value = {"ContentLength": 1024}

        result = await mock_s3_client.check_object_exists(s3_key)

        assert result is True
        mock_s3_client._client.head_object.assert_called_once_with(
            Bucket=mock_s3_client.bucket_name, Key=s3_key
        )

    @pytest.mark.asyncio()
    async def test_check_object_exists_false(self, mock_s3_client):
        """Test checking if object exists (not exists case)."""
        s3_key = "test/file.txt"

        mock_s3_client._client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "HeadObject"
        )

        result = await mock_s3_client.check_object_exists(s3_key)

        assert result is False

    @pytest.mark.asyncio()
    async def test_get_object_metadata(self, mock_s3_client):
        """Test getting object metadata."""
        s3_key = "test/file.txt"

        mock_s3_client._client.head_object.return_value = {
            "ContentLength": 1024,
            "LastModified": "2023-01-01T00:00:00Z",
            "ETag": '"abc123"',
            "ContentType": "text/plain",
            "Metadata": {"custom": "value"},
        }

        result = await mock_s3_client.get_object_metadata(s3_key)

        assert result["size"] == 1024
        assert result["etag"] == "abc123"
        assert result["content_type"] == "text/plain"
        assert result["metadata"] == {"custom": "value"}

    @pytest.mark.asyncio()
    async def test_copy_object(self, mock_s3_client):
        """Test copying an object."""
        source_key = "source/file.txt"
        dest_key = "dest/file.txt"

        result = await mock_s3_client.copy_object(source_key, dest_key)

        assert result == dest_key
        mock_s3_client._client.copy_object.assert_called_once_with(
            CopySource={"Bucket": mock_s3_client.bucket_name, "Key": source_key},
            Bucket=mock_s3_client.bucket_name,
            Key=dest_key,
        )

    @pytest.mark.asyncio()
    async def test_upload_file_small(self, mock_s3_client):
        """Test uploading a small file (no multipart)."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            s3_key = "test/small_file.txt"

            # Mock file reading
            with patch("aiofiles.open", create=True) as mock_open:
                mock_file = AsyncMock()
                mock_file.read.return_value = b"test content"
                mock_open.return_value.__aenter__.return_value = mock_file

                result = await mock_s3_client.upload_file(temp_path, s3_key)

                assert result == s3_key
                mock_s3_client._client.put_object.assert_called_once()

        finally:
            temp_path.unlink()

    @pytest.mark.asyncio()
    async def test_download_file(self, mock_s3_client):
        """Test downloading a file."""
        s3_key = "test/file.txt"

        with tempfile.TemporaryDirectory() as temp_dir:
            download_path = Path(temp_dir) / "downloaded.txt"

            # Mock response
            mock_s3_client._client.head_object.return_value = {"ContentLength": 12}

            # Create an async iterator for chunks
            async def async_iter_chunks(chunk_size=None):
                for chunk in [b"test", b" ", b"content"]:
                    yield chunk

            mock_body = AsyncMock()
            mock_body.iter_chunks = async_iter_chunks
            mock_s3_client._client.get_object.return_value = {"Body": mock_body}

            # Mock file writing
            with patch("aiofiles.open", create=True) as mock_open:
                mock_file = AsyncMock()
                mock_open.return_value.__aenter__.return_value = mock_file

                result = await mock_s3_client.download_file(s3_key, download_path)

                assert result == download_path
                assert mock_file.write.call_count == 3  # 3 chunks

                # Verify chunks were written
                expected_chunks = [b"test", b" ", b"content"]
                for i, chunk in enumerate(expected_chunks):
                    assert mock_file.write.call_args_list[i][0][0] == chunk


@pytest.mark.asyncio()
class TestS3ClientMultipart:
    """Test multipart upload functionality."""

    async def test_upload_file_large_multipart(self, mock_s3_client):
        """Test uploading a large file using multipart upload."""
        # Create a large temporary file
        file_size = 20 * 1024 * 1024  # 20MB
        chunk_size = 10 * 1024 * 1024  # 10MB chunks

        with tempfile.NamedTemporaryFile(delete=False) as f:
            # Write some data (not full size for test)
            f.write(b"x" * 100)
            temp_path = Path(f.name)

        try:
            s3_key = "test/large_file.bin"
            upload_id = "test-upload-id"

            # Mock file stats to report large size
            with patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value.st_size = file_size

                # Configure S3 client for multipart
                mock_s3_client.multipart_threshold = chunk_size
                mock_s3_client.multipart_chunksize = chunk_size

                # Mock multipart operations
                mock_s3_client._client.create_multipart_upload.return_value = {
                    "UploadId": upload_id
                }
                mock_s3_client._client.upload_part.return_value = {"ETag": '"part-etag"'}
                mock_s3_client._client.complete_multipart_upload.return_value = {}

                # Mock file reading
                with patch("aiofiles.open", create=True) as mock_open:
                    mock_file = AsyncMock()
                    # Simulate reading chunks
                    mock_file.read.side_effect = [
                        b"x" * chunk_size,  # First chunk
                        b"x" * chunk_size,  # Second chunk
                        b"",  # EOF
                    ]
                    mock_open.return_value.__aenter__.return_value = mock_file

                    # Test with progress callback
                    progress_updates = []

                    def progress_callback(bytes_uploaded):
                        progress_updates.append(bytes_uploaded)

                    result = await mock_s3_client.upload_file(
                        temp_path, s3_key, progress_callback=progress_callback
                    )

                    assert result == s3_key

                    # Verify multipart upload was initiated
                    mock_s3_client._client.create_multipart_upload.assert_called_once()

                    # Verify parts were uploaded
                    assert mock_s3_client._client.upload_part.call_count == 2

                    # Verify multipart upload was completed
                    mock_s3_client._client.complete_multipart_upload.assert_called_once()

                    # Verify progress updates
                    assert len(progress_updates) == 2
                    assert progress_updates[0] == chunk_size
                    assert progress_updates[1] == chunk_size * 2

        finally:
            temp_path.unlink()

    async def test_multipart_upload_failure(self, mock_s3_client):
        """Test multipart upload failure and cleanup."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 100)
            temp_path = Path(f.name)

        try:
            s3_key = "test/large_file.bin"
            upload_id = "test-upload-id"

            # Mock file stats
            with patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value.st_size = 20 * 1024 * 1024

                mock_s3_client.multipart_threshold = 10 * 1024 * 1024

                # Mock multipart operations
                mock_s3_client._client.create_multipart_upload.return_value = {
                    "UploadId": upload_id
                }
                # Make upload_part fail
                mock_s3_client._client.upload_part.side_effect = ClientError(
                    {"Error": {"Code": "InternalError"}}, "UploadPart"
                )

                # Mock file reading
                with patch("aiofiles.open", create=True) as mock_open:
                    mock_file = AsyncMock()
                    mock_file.read.return_value = b"x" * (10 * 1024 * 1024)
                    mock_open.return_value.__aenter__.return_value = mock_file

                    # Should raise the error
                    with pytest.raises(ClientError):
                        await mock_s3_client.upload_file(temp_path, s3_key)

                    # Verify multipart upload was aborted (called 3 times due to retry logic)
                    assert mock_s3_client._client.abort_multipart_upload.call_count == 3
                    mock_s3_client._client.abort_multipart_upload.assert_called_with(
                        Bucket=mock_s3_client.bucket_name, Key=s3_key, UploadId=upload_id
                    )

        finally:
            temp_path.unlink()


@pytest.mark.asyncio()
class TestS3ClientIntegration:
    """Integration tests with real MinIO (if available)."""

    @pytest.mark.skip(reason="Requires MinIO to be running")
    async def test_real_upload_download(self):
        """Test real upload and download with MinIO."""
        async with S3Client() as client:
            # Create bucket
            await client.create_bucket_if_not_exists()

            # Test data
            run_id = uuid4()
            test_data = {"message": "Hello, PenEllE!", "run_id": str(run_id)}

            # Upload JSON
            s3_key = f"{StoragePaths.planning(run_id)}/plan.json"
            await client.upload_json(test_data, s3_key)

            # Download JSON
            downloaded = await client.download_json(s3_key)
            assert downloaded == test_data

            # Check exists
            assert await client.check_object_exists(s3_key)

            # List objects
            objects = await client.list_objects(prefix=StoragePaths.run_base(run_id))
            assert len(objects) == 1
            assert objects[0]["key"] == s3_key

            # Generate presigned URL
            url = await client.generate_presigned_url(s3_key)
            assert url.startswith("http")

            # Delete object
            await client.delete_object(s3_key)
            assert not await client.check_object_exists(s3_key)
