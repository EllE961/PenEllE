"""Tests for file manager and processor."""

import asyncio
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pypdf import PdfWriter

from src.core.storage.file_manager import FileManager, FileProcessor, SecurityError, ValidationError


@pytest.fixture()
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture()
def file_manager(temp_dir):
    """Create a FileManager instance."""
    return FileManager(temp_dir=temp_dir)


@pytest.fixture()
def mock_artifact_store():
    """Create a mock artifact store."""
    store = MagicMock()
    store.save_artifact = AsyncMock()
    return store


@pytest.fixture()
def file_processor(file_manager, mock_artifact_store):
    """Create a FileProcessor instance."""
    return FileProcessor(file_manager, mock_artifact_store)


class TestFileManager:
    """Test FileManager functionality."""

    def test_read_write_file(self, file_manager, temp_dir):
        """Test reading and writing files."""
        # Write file
        test_path = temp_dir / "test.bin"
        content = b"Binary content"

        result = file_manager.write_file(test_path, content)
        assert result == test_path
        assert test_path.exists()

        # Read file
        read_content = file_manager.read_file(test_path)
        assert read_content == content

    def test_read_write_text_file(self, file_manager, temp_dir):
        """Test reading and writing text files."""
        # Write text file
        test_path = temp_dir / "test.txt"
        content = "Hello, world! 🌍"

        result = file_manager.write_text_file(test_path, content)
        assert result == test_path
        assert test_path.exists()

        # Read text file
        read_content = file_manager.read_text_file(test_path)
        assert read_content == content

    def test_copy_move_file(self, file_manager, temp_dir):
        """Test copying and moving files."""
        # Create source file
        src_path = temp_dir / "source.txt"
        content = "Test content"
        file_manager.write_text_file(src_path, content)

        # Copy file
        copy_path = temp_dir / "copy.txt"
        result = file_manager.copy_file(src_path, copy_path)
        assert result == copy_path
        assert copy_path.exists()
        assert src_path.exists()  # Original still exists
        assert file_manager.read_text_file(copy_path) == content

        # Move file
        move_path = temp_dir / "moved.txt"
        result = file_manager.move_file(src_path, move_path)
        assert result == move_path
        assert move_path.exists()
        assert not src_path.exists()  # Original removed
        assert file_manager.read_text_file(move_path) == content

    def test_delete_file(self, file_manager, temp_dir):
        """Test deleting files."""
        # Create file
        test_path = temp_dir / "delete_me.txt"
        file_manager.write_text_file(test_path, "Delete this")
        assert test_path.exists()

        # Delete file
        file_manager.delete_file(test_path)
        assert not test_path.exists()

        # Try to delete non-existent file
        with pytest.raises(FileNotFoundError):
            file_manager.delete_file(test_path)

    def test_get_file_info(self, file_manager, temp_dir):
        """Test getting file information."""
        # Create file
        test_path = temp_dir / "info_test.json"
        content = '{"test": true}'
        file_manager.write_text_file(test_path, content)

        # Get info
        info = file_manager.get_file_info(test_path)

        assert info["name"] == "info_test.json"
        assert info["size"] == len(content)
        assert info["mime_type"] == "application/json"
        assert info["extension"] == ".json"
        assert info["is_file"] is True
        assert info["is_dir"] is False
        assert isinstance(info["created"], datetime)
        assert isinstance(info["modified"], datetime)

    def test_validate_file(self, file_manager, temp_dir):
        """Test file validation."""
        # Create test files
        pdf_path = temp_dir / "test.pdf"
        txt_path = temp_dir / "test.txt"
        large_path = temp_dir / "large.bin"

        file_manager.write_file(pdf_path, b"PDF content")
        file_manager.write_text_file(txt_path, "Text content")
        file_manager.write_file(large_path, b"x" * 1000)

        # Valid cases
        assert file_manager.validate_file(pdf_path, allowed_extensions=[".pdf"])
        assert file_manager.validate_file(txt_path, max_size=1000)

        # Invalid extension
        with pytest.raises(ValidationError, match="extension.*not allowed"):
            file_manager.validate_file(pdf_path, allowed_extensions=[".txt"])

        # File too large
        with pytest.raises(ValidationError, match="exceeds maximum"):
            file_manager.validate_file(large_path, max_size=100)

        # Not a file
        with pytest.raises(ValidationError, match="not a file"):
            file_manager.validate_file(temp_dir)

    def test_temp_file_operations(self, file_manager):
        """Test temporary file operations."""
        # Create temp file
        content = b"Temporary content"
        temp_path = file_manager.create_temp_file(content, suffix=".tmp")

        assert temp_path.exists()
        assert temp_path.suffix == ".tmp"
        assert file_manager.read_file(temp_path) == content
        assert temp_path in file_manager._temp_files

        # Cleanup
        cleaned = file_manager.cleanup_temp_files()
        assert cleaned >= 1
        assert not temp_path.exists()
        assert temp_path not in file_manager._temp_files

    def test_context_manager(self, temp_dir):
        """Test FileManager as context manager."""
        temp_path = None

        with FileManager(temp_dir=temp_dir) as fm:
            # Create temp file
            temp_path = fm.create_temp_file(b"Context test")
            assert temp_path.exists()

        # Should be cleaned up after context
        assert not temp_path.exists()

    def test_zip_operations(self, file_manager, temp_dir):
        """Test zip file operations."""
        # Create test files
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        file3 = subdir / "file3.txt"

        file_manager.write_text_file(file1, "Content 1")
        file_manager.write_text_file(file2, "Content 2")
        file_manager.write_text_file(file3, "Content 3")

        # Create zip
        zip_path = temp_dir / "test.zip"
        result = file_manager.create_zip([file1, file2, subdir], zip_path)
        assert result == zip_path
        assert zip_path.exists()

        # Extract zip
        extract_dir = temp_dir / "extracted"
        extracted = file_manager.extract_zip(zip_path, extract_dir)

        assert len(extracted) == 3
        assert (extract_dir / "file1.txt").exists()
        assert (extract_dir / "file2.txt").exists()
        assert (extract_dir / "subdir" / "file3.txt").exists()

        # Verify content
        assert file_manager.read_text_file(extract_dir / "file1.txt") == "Content 1"

    def test_checksum_calculation(self, file_manager, temp_dir):
        """Test checksum calculation."""
        # Create file
        test_path = temp_dir / "checksum_test.txt"
        content = "Test content for checksum"
        file_manager.write_text_file(test_path, content)

        # Calculate checksums
        sha256 = file_manager.calculate_checksum(test_path, "sha256")
        sha1 = file_manager.calculate_checksum(test_path, "sha1")
        md5 = file_manager.calculate_checksum(test_path, "md5")

        # Verify format
        assert len(sha256) == 64  # SHA256 is 256 bits = 64 hex chars
        assert len(sha1) == 40  # SHA1 is 160 bits = 40 hex chars
        assert len(md5) == 32  # MD5 is 128 bits = 32 hex chars

        # Same content should give same hash
        sha256_2 = file_manager.calculate_checksum(test_path, "sha256")
        assert sha256 == sha256_2

        # Invalid algorithm
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            file_manager.calculate_checksum(test_path, "invalid")

    @pytest.mark.asyncio()
    async def test_async_file_operations(self, file_manager, temp_dir):
        """Test async file operations."""
        # Async write
        test_path = temp_dir / "async_test.txt"
        content = "Async content"

        result = await file_manager.async_write_text_file(test_path, content)
        assert result == test_path
        assert test_path.exists()

        # Async read
        read_content = await file_manager.async_read_text_file(test_path)
        assert read_content == content

        # Async copy
        copy_path = temp_dir / "async_copy.txt"
        result = await file_manager.async_copy_file(test_path, copy_path)
        assert result == copy_path
        assert copy_path.exists()

        # Async checksum
        checksum = await file_manager.async_calculate_checksum(test_path)
        assert len(checksum) == 64


class TestFileManagerSecurity:
    """Test security features of FileManager."""

    def test_path_traversal_prevention(self, file_manager, temp_dir):
        """Test prevention of path traversal attacks."""
        # Try to access parent directory
        with pytest.raises((SecurityError, FileNotFoundError)):
            file_manager.read_file("../../../etc/passwd")

        # Try to use absolute path outside allowed
        with pytest.raises((SecurityError, FileNotFoundError)):
            file_manager.read_file("/etc/passwd")

        # Allowed paths should work
        test_path = temp_dir / "allowed.txt"
        file_manager.write_text_file(test_path, "Allowed")
        content = file_manager.read_text_file(test_path)
        assert content == "Allowed"

    def test_zip_slip_prevention(self, file_manager, temp_dir):
        """Test prevention of zip slip vulnerability."""
        # Create a malicious zip file
        zip_path = temp_dir / "malicious.zip"

        with zipfile.ZipFile(zip_path, "w") as zf:
            # Try to write file with path traversal
            zf.writestr("../../../tmp/evil.txt", "Evil content")

        # Should raise SecurityError when extracting
        extract_dir = temp_dir / "extract"
        with pytest.raises(SecurityError, match="Zip slip"):
            file_manager.extract_zip(zip_path, extract_dir)


class TestFileProcessor:
    """Test FileProcessor functionality."""

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        # Test various problematic filenames
        assert FileProcessor.sanitize_filename("normal.txt") == "normal.txt"
        assert FileProcessor.sanitize_filename("with spaces.pdf") == "with spaces.pdf"
        assert FileProcessor.sanitize_filename("../../../etc/passwd") == "passwd"
        assert FileProcessor.sanitize_filename("file<>:|?*.txt") == "file______.txt"
        assert FileProcessor.sanitize_filename("   .hidden.  ") == "hidden"
        assert FileProcessor.sanitize_filename("") == "unnamed_file"

        # Test length limit
        long_name = "a" * 300 + ".txt"
        sanitized = FileProcessor.sanitize_filename(long_name)
        assert len(sanitized) <= 255
        assert sanitized.endswith(".txt")

    def test_process_pdf(self, file_processor, temp_dir):
        """Test PDF processing."""
        # Create a simple PDF
        pdf_path = temp_dir / "test.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)

        # Add metadata
        writer.add_metadata(
            {"/Title": "Test PDF", "/Author": "Test Author", "/Subject": "Test Subject"}
        )

        with open(pdf_path, "wb") as f:
            writer.write(f)

        # Process PDF
        result = file_processor.process_pdf(pdf_path)

        assert result["pages"] == 1
        assert result["encrypted"] is False
        assert "info" in result
        # Metadata extraction might vary by pypdf version

    def test_process_pdf_invalid(self, file_processor, temp_dir):
        """Test processing invalid PDF."""
        # Create non-PDF file
        fake_pdf = temp_dir / "fake.pdf"
        file_processor.file_manager.write_text_file(fake_pdf, "Not a PDF")

        # Should raise ValidationError
        with pytest.raises(ValidationError, match="Invalid PDF"):
            file_processor.process_pdf(fake_pdf)

    @pytest.mark.asyncio()
    async def test_process_user_upload(self, file_processor, temp_dir, mock_artifact_store):
        """Test processing user uploads."""
        # Create test file
        upload_path = temp_dir / "upload.txt"
        content = "User uploaded content"
        file_processor.file_manager.write_text_file(upload_path, content)

        # Process upload
        user_id = uuid4()
        run_id = uuid4()

        result = await file_processor.process_user_upload(upload_path, user_id, run_id)

        assert result["original_filename"] == "upload.txt"
        assert result["size"] == len(content)
        assert result["mime_type"] == "text/plain"
        assert "checksum" in result
        assert result["user_id"] == str(user_id)
        assert "uploaded_at" in result
        assert result["stored_as"] == "user_library/upload.txt"

        # Verify artifact store was called
        mock_artifact_store.save_artifact.assert_called_once()
        call_args = mock_artifact_store.save_artifact.call_args
        assert call_args.kwargs["run_id"] == run_id
        assert call_args.kwargs["stage"] == "user_library"
        assert call_args.kwargs["filename"] == "upload.txt"

    @pytest.mark.asyncio()
    async def test_process_user_upload_validation(self, file_processor, temp_dir):
        """Test user upload validation."""
        # Create file with disallowed extension
        bad_file = temp_dir / "bad.exe"
        file_processor.file_manager.write_file(bad_file, b"Executable")

        # Should raise ValidationError
        with pytest.raises(ValidationError, match="extension.*not allowed"):
            await file_processor.process_user_upload(bad_file, uuid4(), uuid4())

        # Create file that's too large
        with patch("src.core.config.settings.MAX_UPLOAD_SIZE", 10):
            large_file = temp_dir / "large.txt"
            file_processor.file_manager.write_file(large_file, b"x" * 100)

            with pytest.raises(ValidationError, match="exceeds maximum"):
                await file_processor.process_user_upload(large_file, uuid4(), uuid4())

    def test_validate_research_paper(self, file_processor, temp_dir):
        """Test research paper validation."""
        # Create a PDF that looks like a research paper
        pdf_path = temp_dir / "paper.pdf"
        writer = PdfWriter()

        # Add multiple pages
        for i in range(10):
            writer.add_blank_page(width=595, height=842)  # A4 size

        with open(pdf_path, "wb") as f:
            writer.write(f)

        # Should validate as research paper (has many pages)
        assert file_processor.validate_research_paper(pdf_path) is True

        # Create a short PDF
        short_pdf = temp_dir / "short.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)

        with open(short_pdf, "wb") as f:
            writer.write(f)

        # Should not validate (too few pages)
        assert file_processor.validate_research_paper(short_pdf) is False

        # Non-PDF should not validate
        txt_file = temp_dir / "not_pdf.txt"
        file_processor.file_manager.write_text_file(txt_file, "Not a PDF")
        assert file_processor.validate_research_paper(txt_file) is False


@pytest.mark.asyncio()
class TestFileManagerConcurrency:
    """Test concurrent file operations."""

    async def test_concurrent_writes(self, file_manager, temp_dir):
        """Test concurrent file writes."""
        # Create multiple tasks writing different files
        tasks = []
        for i in range(10):
            path = temp_dir / f"concurrent_{i}.txt"
            content = f"Content {i}"
            task = file_manager.async_write_text_file(path, content)
            tasks.append(task)

        # Wait for all writes
        results = await asyncio.gather(*tasks)

        # Verify all files exist with correct content
        for i, result in enumerate(results):
            assert result.name == f"concurrent_{i}.txt"
            content = await file_manager.async_read_text_file(result)
            assert content == f"Content {i}"

    async def test_concurrent_checksums(self, file_manager, temp_dir):
        """Test concurrent checksum calculations."""
        # Create test file
        test_path = temp_dir / "checksum_test.bin"
        content = b"x" * 10000  # 10KB
        await file_manager.async_write_file(test_path, content)

        # Calculate checksum multiple times concurrently
        tasks = []
        for _ in range(5):
            task = file_manager.async_calculate_checksum(test_path)
            tasks.append(task)

        # All should return same checksum
        checksums = await asyncio.gather(*tasks)
        assert len(set(checksums)) == 1  # All same
