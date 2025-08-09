"""File management and processing utilities."""

import asyncio
import hashlib
import logging
import mimetypes
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from uuid import UUID

import aiofiles
import aiofiles.os
from pypdf import PdfReader

from src.core.config import settings
from src.core.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security violation is detected."""

    pass


class ValidationError(Exception):
    """Raised when file validation fails."""

    pass


class FileManager:
    """Manages file operations with security and validation."""

    def __init__(self, temp_dir: Optional[Path] = None):
        """Initialize file manager.

        Args:
            temp_dir: Custom temp directory path
        """
        self.temp_dir = Path(temp_dir or settings.TEMP_DIR)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._temp_files: Set[Path] = set()

        # Initialize mimetypes
        mimetypes.init()

    def __enter__(self) -> "FileManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - cleanup temp files."""
        self.cleanup_temp_files()

    def _validate_path(self, path: Union[str, Path]) -> Path:
        """Validate path for security issues.

        Args:
            path: Path to validate

        Returns:
            Resolved absolute path

        Raises:
            SecurityError: If path contains security issues
        """
        path = Path(path).resolve()

        # Check for path traversal attempts
        try:
            # Ensure the resolved path is within expected boundaries
            path.relative_to(Path.cwd())
        except ValueError:
            # Path is outside current directory - additional checks needed
            if not any(
                str(path).startswith(str(allowed))
                for allowed in [self.temp_dir, Path.home(), "/tmp", "/var/tmp"]
            ):
                raise SecurityError(f"Path traversal attempt detected: {path}")

        return path

    def read_file(self, path: Union[str, Path]) -> bytes:
        """Read a file as bytes.

        Args:
            path: File path

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
            SecurityError: If path is invalid
        """
        path = self._validate_path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        return path.read_bytes()

    def write_file(self, path: Union[str, Path], content: bytes) -> Path:
        """Write bytes to a file.

        Args:
            path: File path
            content: Content to write

        Returns:
            Path to written file

        Raises:
            SecurityError: If path is invalid
        """
        path = self._validate_path(path)

        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_bytes(content)
        logger.info(f"Wrote {len(content)} bytes to {path}")

        return path

    def read_text_file(self, path: Union[str, Path], encoding: str = "utf-8") -> str:
        """Read a text file.

        Args:
            path: File path
            encoding: Text encoding

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file doesn't exist
            SecurityError: If path is invalid
        """
        content = self.read_file(path)
        return content.decode(encoding)

    def write_text_file(
        self, path: Union[str, Path], content: str, encoding: str = "utf-8"
    ) -> Path:
        """Write text to a file.

        Args:
            path: File path
            content: Text content
            encoding: Text encoding

        Returns:
            Path to written file

        Raises:
            SecurityError: If path is invalid
        """
        return self.write_file(path, content.encode(encoding))

    def copy_file(self, src: Union[str, Path], dst: Union[str, Path]) -> Path:
        """Copy a file.

        Args:
            src: Source file path
            dst: Destination file path

        Returns:
            Path to copied file

        Raises:
            FileNotFoundError: If source doesn't exist
            SecurityError: If paths are invalid
        """
        src = self._validate_path(src)
        dst = self._validate_path(dst)

        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")

        # Create parent directories if needed
        dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src, dst)
        logger.info(f"Copied {src} to {dst}")

        return dst

    def move_file(self, src: Union[str, Path], dst: Union[str, Path]) -> Path:
        """Move a file.

        Args:
            src: Source file path
            dst: Destination file path

        Returns:
            Path to moved file

        Raises:
            FileNotFoundError: If source doesn't exist
            SecurityError: If paths are invalid
        """
        src = self._validate_path(src)
        dst = self._validate_path(dst)

        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")

        # Create parent directories if needed
        dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(src), str(dst))
        logger.info(f"Moved {src} to {dst}")

        return dst

    def delete_file(self, path: Union[str, Path]) -> None:
        """Delete a file.

        Args:
            path: File path

        Raises:
            FileNotFoundError: If file doesn't exist
            SecurityError: If path is invalid
        """
        path = self._validate_path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

        logger.info(f"Deleted {path}")

    def get_file_info(self, path: Union[str, Path]) -> Dict[str, Any]:
        """Get file information.

        Args:
            path: File path

        Returns:
            Dictionary with file info

        Raises:
            FileNotFoundError: If file doesn't exist
            SecurityError: If path is invalid
        """
        path = self._validate_path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        stat = path.stat()
        mime_type, _ = mimetypes.guess_type(str(path))

        return {
            "path": str(path),
            "name": path.name,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime, timezone.utc),
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc),
            "mime_type": mime_type,
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "extension": path.suffix.lower(),
        }

    def validate_file(
        self,
        path: Union[str, Path],
        allowed_extensions: Optional[List[str]] = None,
        max_size: Optional[int] = None,
    ) -> bool:
        """Validate a file.

        Args:
            path: File path
            allowed_extensions: List of allowed extensions (with dots)
            max_size: Maximum file size in bytes

        Returns:
            True if valid

        Raises:
            ValidationError: If validation fails
            FileNotFoundError: If file doesn't exist
            SecurityError: If path is invalid
        """
        info = self.get_file_info(path)

        # Check if it's a file
        if not info["is_file"]:
            raise ValidationError(f"Path is not a file: {path}")

        # Check extension
        if allowed_extensions:
            if info["extension"] not in allowed_extensions:
                raise ValidationError(
                    f"File extension {info['extension']} not allowed. "
                    f"Allowed: {allowed_extensions}"
                )

        # Check size
        if max_size and info["size"] > max_size:
            raise ValidationError(f"File size {info['size']} exceeds maximum {max_size}")

        return True

    def create_temp_file(self, content: bytes, suffix: Optional[str] = None) -> Path:
        """Create a temporary file.

        Args:
            content: File content
            suffix: File suffix (e.g., '.txt')

        Returns:
            Path to temp file
        """
        with tempfile.NamedTemporaryFile(dir=self.temp_dir, suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            temp_path = Path(tmp.name)

        self._temp_files.add(temp_path)
        logger.debug(f"Created temp file: {temp_path}")

        return temp_path

    def cleanup_temp_files(self) -> int:
        """Clean up temporary files.

        Returns:
            Number of files cleaned up
        """
        cleaned = 0

        # Clean tracked temp files
        for temp_file in list(self._temp_files):
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    cleaned += 1
                self._temp_files.remove(temp_file)
            except Exception as e:
                logger.error(f"Failed to clean up {temp_file}: {e}")

        # Clean old files in temp directory
        if self.temp_dir.exists():
            cutoff_time = datetime.now(timezone.utc).timestamp() - settings.FILE_CLEANUP_AGE

            for file_path in self.temp_dir.rglob("*"):
                try:
                    if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                        file_path.unlink()
                        cleaned += 1
                except Exception as e:
                    logger.error(f"Failed to clean up old file {file_path}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} temporary files")

        return cleaned

    def extract_zip(self, zip_path: Union[str, Path], extract_to: Union[str, Path]) -> List[Path]:
        """Extract a zip file.

        Args:
            zip_path: Path to zip file
            extract_to: Directory to extract to

        Returns:
            List of extracted file paths

        Raises:
            ValidationError: If not a valid zip file
            SecurityError: If paths are invalid
        """
        zip_path = self._validate_path(zip_path)
        extract_to = self._validate_path(extract_to)

        if not zipfile.is_zipfile(zip_path):
            raise ValidationError(f"Not a valid zip file: {zip_path}")

        extract_to.mkdir(parents=True, exist_ok=True)
        extracted_files = []

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                # Security check for zip slip vulnerability
                # Normalize the path and ensure it doesn't escape
                member_path = (Path(extract_to) / member).resolve()
                try:
                    member_path.relative_to(Path(extract_to).resolve())
                except ValueError:
                    raise SecurityError(f"Zip slip attempt detected: {member}")

                zip_ref.extract(member, extract_to)
                extracted_files.append(member_path)

        logger.info(f"Extracted {len(extracted_files)} files from {zip_path}")
        return extracted_files

    def create_zip(self, files: List[Union[str, Path]], output_path: Union[str, Path]) -> Path:
        """Create a zip file.

        Args:
            files: List of files to zip
            output_path: Output zip file path

        Returns:
            Path to created zip file

        Raises:
            FileNotFoundError: If any input file doesn't exist
            SecurityError: If paths are invalid
        """
        output_path = self._validate_path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
            for file_path in files:
                file_path = self._validate_path(file_path)

                if not file_path.exists():
                    raise FileNotFoundError(f"File not found: {file_path}")

                if file_path.is_file():
                    zip_ref.write(file_path, file_path.name)
                elif file_path.is_dir():
                    for sub_path in file_path.rglob("*"):
                        if sub_path.is_file():
                            arcname = sub_path.relative_to(file_path.parent)
                            zip_ref.write(sub_path, arcname)

        logger.info(f"Created zip file: {output_path}")
        return output_path

    def calculate_checksum(self, path: Union[str, Path], algorithm: str = "sha256") -> str:
        """Calculate file checksum.

        Args:
            path: File path
            algorithm: Hash algorithm (sha256, sha1, md5)

        Returns:
            Hex digest of checksum

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If algorithm not supported
            SecurityError: If path is invalid
        """
        path = self._validate_path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if algorithm not in hashlib.algorithms_available:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        hash_obj = hashlib.new(algorithm)

        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)

        return hash_obj.hexdigest()

    # Async versions of file operations

    async def async_read_file(self, path: Union[str, Path]) -> bytes:
        """Async read a file as bytes."""
        path = self._validate_path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        async with aiofiles.open(path, "rb") as f:
            content: bytes = await f.read()
            return content

    async def async_write_file(self, path: Union[str, Path], content: bytes) -> Path:
        """Async write bytes to a file."""
        path = self._validate_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, "wb") as f:
            await f.write(content)

        logger.info(f"Async wrote {len(content)} bytes to {path}")
        return path

    async def async_read_text_file(self, path: Union[str, Path], encoding: str = "utf-8") -> str:
        """Async read a text file."""
        path = self._validate_path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        async with aiofiles.open(path, "r", encoding=encoding) as f:
            text: str = await f.read()
            return text

    async def async_write_text_file(
        self, path: Union[str, Path], content: str, encoding: str = "utf-8"
    ) -> Path:
        """Async write text to a file."""
        path = self._validate_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, "w", encoding=encoding) as f:
            await f.write(content)

        logger.info(f"Async wrote text to {path}")
        return path

    async def async_copy_file(self, src: Union[str, Path], dst: Union[str, Path]) -> Path:
        """Async copy a file."""
        src = self._validate_path(src)
        dst = self._validate_path(dst)

        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")

        dst.parent.mkdir(parents=True, exist_ok=True)

        # Use asyncio to run in thread pool
        await asyncio.get_event_loop().run_in_executor(None, shutil.copy2, str(src), str(dst))

        logger.info(f"Async copied {src} to {dst}")
        return dst

    async def async_calculate_checksum(
        self, path: Union[str, Path], algorithm: str = "sha256"
    ) -> str:
        """Async calculate file checksum."""
        path = self._validate_path(path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if algorithm not in hashlib.algorithms_available:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        hash_obj = hashlib.new(algorithm)

        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(8192):
                hash_obj.update(chunk)

        return hash_obj.hexdigest()


class FileProcessor:
    """Process files for the pipeline."""

    def __init__(self, file_manager: FileManager, artifact_store: Optional[ArtifactStore] = None):
        """Initialize file processor.

        Args:
            file_manager: FileManager instance
            artifact_store: Optional ArtifactStore for saving processed files
        """
        self.file_manager = file_manager
        self.artifact_store = artifact_store

    def process_pdf(self, path: Union[str, Path]) -> Dict[str, Any]:
        """Extract metadata from a PDF file.

        Args:
            path: Path to PDF file

        Returns:
            Dictionary with PDF metadata

        Raises:
            ValidationError: If not a valid PDF
        """
        path = Path(path)

        # Validate it's a PDF
        self.file_manager.validate_file(
            path, allowed_extensions=[".pdf"], max_size=settings.MAX_FILE_SIZE
        )

        try:
            reader = PdfReader(path)

            metadata: Dict[str, Any] = {
                "pages": len(reader.pages),
                "encrypted": reader.is_encrypted,
                "info": {},
            }

            # Extract document info
            if reader.metadata:
                info_fields = [
                    "title",
                    "author",
                    "subject",
                    "creator",
                    "producer",
                    "creation_date",
                    "modification_date",
                ]
                for field in info_fields:
                    value = getattr(reader.metadata, field, None)
                    if value:
                        metadata["info"][field] = str(value)

            # Extract text from first page (sample)
            if reader.pages:
                first_page_text = reader.pages[0].extract_text()
                metadata["first_page_preview"] = first_page_text[:500]

            return metadata

        except Exception as e:
            raise ValidationError(f"Invalid PDF file: {e}")

    async def process_user_upload(
        self, file_path: Union[str, Path], user_id: Union[str, UUID], run_id: Union[str, UUID]
    ) -> Dict[str, Any]:
        """Process a user-uploaded file.

        Args:
            file_path: Path to uploaded file
            user_id: User ID
            run_id: Run ID

        Returns:
            Processing result with metadata

        Raises:
            ValidationError: If file validation fails
        """
        file_path = Path(file_path)
        user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id
        run_id = UUID(str(run_id)) if isinstance(run_id, str) else run_id

        # Validate file
        self.file_manager.validate_file(
            file_path,
            allowed_extensions=settings.ALLOWED_UPLOAD_EXTENSIONS,
            max_size=settings.MAX_UPLOAD_SIZE,
        )

        # Get file info
        file_info = self.file_manager.get_file_info(file_path)

        # Calculate checksum
        checksum = await self.file_manager.async_calculate_checksum(file_path)

        # Process based on file type
        metadata = {
            "original_filename": file_info["name"],
            "size": file_info["size"],
            "mime_type": file_info["mime_type"],
            "checksum": checksum,
            "user_id": str(user_id),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

        # Extract additional metadata for PDFs
        if file_info["extension"] == ".pdf":
            try:
                pdf_metadata = self.process_pdf(file_path)
                metadata["pdf_info"] = pdf_metadata
            except Exception as e:
                logger.warning(f"Failed to extract PDF metadata: {e}")

        # Save to artifact store if available
        if self.artifact_store:
            content = await self.file_manager.async_read_file(file_path)

            # Sanitize filename
            safe_filename = self.sanitize_filename(file_info["name"])

            # Save to user library
            await self.artifact_store.save_artifact(
                run_id=run_id,
                stage="user_library",
                filename=safe_filename,
                content=content,
                metadata=metadata,
            )

            metadata["stored_as"] = f"user_library/{safe_filename}"

        return metadata

    def validate_research_paper(self, path: Union[str, Path]) -> bool:
        """Check if a file appears to be a valid academic paper.

        Args:
            path: Path to file

        Returns:
            True if likely a research paper
        """
        path = Path(path)

        # Basic validation
        try:
            self.file_manager.validate_file(
                path, allowed_extensions=[".pdf"], max_size=settings.MAX_FILE_SIZE
            )
        except ValidationError:
            return False

        # Check PDF structure
        try:
            metadata = self.process_pdf(path)

            # Heuristics for research papers
            has_many_pages = metadata["pages"] >= 4
            has_text = "first_page_preview" in metadata

            # Check for common research paper indicators in first page
            if has_text:
                preview = metadata["first_page_preview"].lower()
                research_keywords = [
                    "abstract",
                    "introduction",
                    "methodology",
                    "results",
                    "conclusion",
                    "references",
                    "keywords",
                    "doi",
                    "journal",
                    "conference",
                ]
                has_keywords = any(keyword in preview for keyword in research_keywords)
            else:
                has_keywords = False

            return has_many_pages and (has_text or has_keywords)

        except Exception:
            return False

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize a filename for safe storage.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Remove path components
        filename = os.path.basename(filename)

        # Replace problematic characters
        invalid_chars = '<>:"|?*\x00'
        for char in invalid_chars:
            filename = filename.replace(char, "_")

        # Remove leading/trailing dots and spaces
        filename = filename.strip(". ")

        # Limit length
        max_length = 255
        if len(filename) > max_length:
            name, ext = os.path.splitext(filename)
            filename = name[: max_length - len(ext)] + ext

        # Ensure non-empty
        if not filename:
            filename = "unnamed_file"

        return filename
