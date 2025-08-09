"""S3/MinIO client for artifact storage."""

import json
import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import UUID

import aioboto3
import aiofiles
from botocore.config import Config
from botocore.exceptions import ClientError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import settings

logger = logging.getLogger(__name__)


class StoragePaths:
    """Storage path utilities following PenEllE artifact layout."""

    @staticmethod
    def run_base(run_id: Union[str, UUID]) -> str:
        """Get base path for a run."""
        return f"runs/{run_id}"

    @staticmethod
    def user_library(run_id: Union[str, UUID]) -> str:
        """Get user library path."""
        return f"{StoragePaths.run_base(run_id)}/00_user_library"

    @staticmethod
    def planning(run_id: Union[str, UUID]) -> str:
        """Get planning path."""
        return f"{StoragePaths.run_base(run_id)}/01_planning"

    @staticmethod
    def sourcing(run_id: Union[str, UUID]) -> str:
        """Get sourcing path."""
        return f"{StoragePaths.run_base(run_id)}/02_sourcing"

    @staticmethod
    def retrieval(run_id: Union[str, UUID]) -> str:
        """Get retrieval path."""
        return f"{StoragePaths.run_base(run_id)}/03_retrieval"

    @staticmethod
    def evidence(run_id: Union[str, UUID]) -> str:
        """Get evidence path."""
        return f"{StoragePaths.run_base(run_id)}/04_evidence"

    @staticmethod
    def drafting(run_id: Union[str, UUID]) -> str:
        """Get drafting path."""
        return f"{StoragePaths.run_base(run_id)}/05_drafting"

    @staticmethod
    def humanizing(run_id: Union[str, UUID]) -> str:
        """Get humanizing path."""
        return f"{StoragePaths.run_base(run_id)}/06_humanizing"

    @staticmethod
    def formatting(run_id: Union[str, UUID]) -> str:
        """Get formatting path."""
        return f"{StoragePaths.run_base(run_id)}/07_formatting"

    @staticmethod
    def claim_graph(run_id: Union[str, UUID]) -> str:
        """Get claim graph path."""
        return f"{StoragePaths.run_base(run_id)}/claim_graph"

    @staticmethod
    def quality(run_id: Union[str, UUID]) -> str:
        """Get quality path."""
        return f"{StoragePaths.run_base(run_id)}/quality"

    @staticmethod
    def logs(run_id: Union[str, UUID]) -> str:
        """Get logs path."""
        return f"{StoragePaths.run_base(run_id)}/logs"


class S3Client:
    """Async S3/MinIO client with retry logic and progress tracking."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        region_name: Optional[str] = None,
        use_ssl: Optional[bool] = None,
        verify_ssl: Optional[bool] = None,
        config: Optional[Config] = None,
    ) -> None:
        """Initialize S3 client.

        Args:
            bucket_name: S3 bucket name
            endpoint_url: S3 endpoint URL (for MinIO)
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            region_name: AWS region name
            use_ssl: Whether to use SSL
            verify_ssl: Whether to verify SSL certificates
            config: Boto3 client config
        """
        self.bucket_name = bucket_name or settings.S3_BUCKET_NAME
        self.endpoint_url = endpoint_url or settings.S3_ENDPOINT_URL
        self.access_key_id = access_key_id or settings.S3_ACCESS_KEY_ID
        self.secret_access_key = secret_access_key or settings.S3_SECRET_ACCESS_KEY
        self.region_name = region_name or settings.S3_REGION_NAME
        self.use_ssl = use_ssl if use_ssl is not None else settings.S3_USE_SSL
        self.verify_ssl = verify_ssl if verify_ssl is not None else settings.S3_VERIFY_SSL

        # Configure boto3 client
        self.config = config or Config(
            max_pool_connections=settings.S3_MAX_CONCURRENCY,
            s3={"addressing_style": "path"},  # Required for MinIO
        )

        # Configure multipart settings
        self.multipart_threshold = settings.S3_MULTIPART_THRESHOLD
        self.multipart_chunksize = settings.S3_MULTIPART_CHUNKSIZE

        # Session for creating clients
        self._session = aioboto3.Session()
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> "S3Client":
        """Async context manager entry."""
        self._client = await self._stack.enter_async_context(
            self._session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region_name,
                use_ssl=self.use_ssl,
                verify=self.verify_ssl,
                config=self.config,
            )
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self._stack.aclose()

    def _get_retry_decorator(self, max_attempts: int = 3) -> AsyncRetrying:
        """Get retry decorator for S3 operations."""
        return AsyncRetrying(
            retry=retry_if_exception_type((ClientError, OSError)),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True,
        )

    async def create_bucket_if_not_exists(self) -> bool:
        """Create bucket if it doesn't exist.

        Returns:
            True if bucket was created, False if it already existed
        """
        try:
            await self._client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket {self.bucket_name} already exists")
            return False
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                async for attempt in self._get_retry_decorator():
                    with attempt:
                        await self._client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration=(
                                {"LocationConstraint": self.region_name}
                                if self.region_name != "us-east-1"
                                else {}
                            ),
                        )
                        logger.info(f"Created bucket {self.bucket_name}")
                        return True
                raise RuntimeError("Failed to create bucket after retries")
            else:
                raise

    async def upload_file(
        self,
        file_path: Union[str, Path],
        s3_key: str,
        metadata: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """Upload a file to S3.

        Args:
            file_path: Local file path
            s3_key: S3 object key
            metadata: Optional metadata to attach
            progress_callback: Optional callback for progress updates

        Returns:
            S3 object key
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size

        # Determine if multipart upload is needed
        if file_size > self.multipart_threshold:
            return await self._multipart_upload(file_path, s3_key, metadata, progress_callback)
        else:
            return await self._simple_upload(file_path, s3_key, metadata, progress_callback)

    async def _simple_upload(
        self,
        file_path: Path,
        s3_key: str,
        metadata: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """Simple upload for small files."""
        async for attempt in self._get_retry_decorator():
            with attempt:
                async with aiofiles.open(file_path, "rb") as f:
                    data = await f.read()

                extra_args = {}
                if metadata:
                    extra_args["Metadata"] = metadata

                await self._client.put_object(
                    Bucket=self.bucket_name, Key=s3_key, Body=data, **extra_args
                )

                if progress_callback:
                    progress_callback(file_path.stat().st_size)

                logger.info(f"Uploaded {file_path} to {s3_key}")
                return s3_key
        raise RuntimeError("Failed to upload file after retries")

    async def _multipart_upload(
        self,
        file_path: Path,
        s3_key: str,
        metadata: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """Multipart upload for large files."""
        # file_size = file_path.stat().st_size  # TODO: Use for progress tracking

        async for attempt in self._get_retry_decorator():
            with attempt:
                # Initiate multipart upload
                extra_args = {}
                if metadata:
                    extra_args["Metadata"] = metadata

                response = await self._client.create_multipart_upload(
                    Bucket=self.bucket_name, Key=s3_key, **extra_args
                )
                upload_id = response["UploadId"]

                parts = []
                uploaded_bytes = 0

                try:
                    async with aiofiles.open(file_path, "rb") as f:
                        part_number = 1
                        while True:
                            data = await f.read(self.multipart_chunksize)
                            if not data:
                                break

                            # Upload part
                            response = await self._client.upload_part(
                                Bucket=self.bucket_name,
                                Key=s3_key,
                                PartNumber=part_number,
                                UploadId=upload_id,
                                Body=data,
                            )

                            parts.append({"ETag": response["ETag"], "PartNumber": part_number})

                            uploaded_bytes += len(data)
                            if progress_callback:
                                progress_callback(uploaded_bytes)

                            part_number += 1

                    # Complete multipart upload
                    await self._client.complete_multipart_upload(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        UploadId=upload_id,
                        MultipartUpload={"Parts": parts},
                    )

                    logger.info(f"Completed multipart upload of {file_path} to {s3_key}")
                    return s3_key

                except Exception:
                    # Abort multipart upload on error
                    await self._client.abort_multipart_upload(
                        Bucket=self.bucket_name, Key=s3_key, UploadId=upload_id
                    )
                    raise
        raise RuntimeError("Failed to complete multipart upload after retries")

    async def download_file(
        self,
        s3_key: str,
        file_path: Union[str, Path],
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Path:
        """Download a file from S3.

        Args:
            s3_key: S3 object key
            file_path: Local file path to save to
            progress_callback: Optional callback for progress updates

        Returns:
            Path to downloaded file
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async for attempt in self._get_retry_decorator():
            with attempt:
                # Get object size
                response = await self._client.head_object(Bucket=self.bucket_name, Key=s3_key)
                # total_size = response["ContentLength"]  # TODO: Use for progress tracking

                # Download object
                response = await self._client.get_object(Bucket=self.bucket_name, Key=s3_key)

                downloaded_bytes = 0
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in response["Body"].iter_chunks(chunk_size=1024 * 1024):
                        await f.write(chunk)
                        downloaded_bytes += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded_bytes)

                logger.info(f"Downloaded {s3_key} to {file_path}")
                return file_path
        raise RuntimeError("Failed to download file after retries")

    async def upload_json(
        self,
        data: Any,
        s3_key: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload JSON data to S3.

        Args:
            data: Data to serialize as JSON
            s3_key: S3 object key
            metadata: Optional metadata to attach

        Returns:
            S3 object key
        """
        json_data = json.dumps(data, indent=2, default=str).encode("utf-8")

        extra_args: Dict[str, Any] = {"ContentType": "application/json"}
        if metadata:
            extra_args["Metadata"] = metadata

        async for attempt in self._get_retry_decorator():
            with attempt:
                await self._client.put_object(
                    Bucket=self.bucket_name, Key=s3_key, Body=json_data, **extra_args
                )

                logger.info(f"Uploaded JSON to {s3_key}")
                return s3_key
        raise RuntimeError("Failed to upload JSON after retries")

    async def download_json(self, s3_key: str) -> Any:
        """Download and parse JSON from S3.

        Args:
            s3_key: S3 object key

        Returns:
            Parsed JSON data
        """
        async for attempt in self._get_retry_decorator():
            with attempt:
                response = await self._client.get_object(Bucket=self.bucket_name, Key=s3_key)

                data = await response["Body"].read()
                logger.info(f"Downloaded JSON from {s3_key}")
                return json.loads(data.decode("utf-8"))
        raise RuntimeError("Failed to download JSON after retries")

    async def list_objects(
        self,
        prefix: Optional[str] = None,
        delimiter: Optional[str] = None,
        max_keys: int = 1000,
    ) -> List[Dict[str, Any]]:
        """List objects in bucket.

        Args:
            prefix: Filter objects by prefix
            delimiter: Delimiter for grouping (e.g., '/')
            max_keys: Maximum number of keys to return

        Returns:
            List of object metadata
        """
        params = {
            "Bucket": self.bucket_name,
            "MaxKeys": max_keys,
        }
        if prefix:
            params["Prefix"] = prefix
        if delimiter:
            params["Delimiter"] = delimiter

        objects = []

        async for attempt in self._get_retry_decorator():
            with attempt:
                continuation_token: str | None = None
                while True:
                    # Set continuation token if we have one from previous iteration
                    list_params = params.copy()
                    if continuation_token is not None:
                        list_params["ContinuationToken"] = continuation_token

                    response = await self._client.list_objects_v2(**list_params)

                    if "Contents" in response:
                        for obj in response["Contents"]:
                            objects.append(
                                {
                                    "key": obj["Key"],
                                    "size": obj["Size"],
                                    "last_modified": obj["LastModified"],
                                    "etag": obj.get("ETag", "").strip('"'),
                                }
                            )

                    if not response.get("IsTruncated"):
                        break

                    continuation_token = response.get("NextContinuationToken")

                logger.info(f"Listed {len(objects)} objects with prefix '{prefix}'")
                return objects
        raise RuntimeError("Failed to list objects after retries")

    async def delete_object(self, s3_key: str) -> bool:
        """Delete an object from S3.

        Args:
            s3_key: S3 object key

        Returns:
            True if deleted successfully
        """
        async for attempt in self._get_retry_decorator():
            with attempt:
                await self._client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                logger.info(f"Deleted object {s3_key}")
                return True
        raise RuntimeError("Failed to delete object after retries")

    async def generate_presigned_url(
        self,
        s3_key: str,
        expiration: Optional[int] = None,
        http_method: str = "GET",
    ) -> str:
        """Generate a presigned URL for temporary access.

        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds
            http_method: HTTP method (GET or PUT)

        Returns:
            Presigned URL
        """
        if expiration is None:
            expiration = settings.S3_PRESIGNED_URL_EXPIRY

        client_method = "get_object" if http_method == "GET" else "put_object"

        async for attempt in self._get_retry_decorator():
            with attempt:
                url: str = await self._client.generate_presigned_url(
                    ClientMethod=client_method,
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": s3_key,
                    },
                    ExpiresIn=expiration,
                )
                logger.info(f"Generated presigned URL for {s3_key}")
                return url
        raise RuntimeError("Failed to generate presigned URL after retries")

    async def check_object_exists(self, s3_key: str) -> bool:
        """Check if an object exists in S3.

        Args:
            s3_key: S3 object key

        Returns:
            True if object exists
        """
        try:
            await self._client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    async def get_object_metadata(self, s3_key: str) -> Dict[str, Any]:
        """Get object metadata.

        Args:
            s3_key: S3 object key

        Returns:
            Object metadata
        """
        async for attempt in self._get_retry_decorator():
            with attempt:
                response = await self._client.head_object(Bucket=self.bucket_name, Key=s3_key)

                return {
                    "size": response["ContentLength"],
                    "last_modified": response["LastModified"],
                    "etag": response.get("ETag", "").strip('"'),
                    "content_type": response.get("ContentType"),
                    "metadata": response.get("Metadata", {}),
                }
        raise RuntimeError("Failed to get object metadata after retries")

    async def copy_object(
        self,
        source_key: str,
        dest_key: str,
        source_bucket: Optional[str] = None,
    ) -> str:
        """Copy an object within S3.

        Args:
            source_key: Source object key
            dest_key: Destination object key
            source_bucket: Source bucket (defaults to current bucket)

        Returns:
            Destination object key
        """
        if source_bucket is None:
            source_bucket = self.bucket_name

        copy_source = {"Bucket": source_bucket, "Key": source_key}

        async for attempt in self._get_retry_decorator():
            with attempt:
                await self._client.copy_object(
                    CopySource=copy_source,
                    Bucket=self.bucket_name,
                    Key=dest_key,
                )
                logger.info(f"Copied {source_key} to {dest_key}")
                return dest_key
        raise RuntimeError("Failed to copy object after retries")
