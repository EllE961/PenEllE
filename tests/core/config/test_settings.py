"""Tests for configuration settings."""


from src.core.config import Settings, settings


class TestSettings:
    """Test cases for Settings configuration."""

    def test_settings_instance(self):
        """Test global settings instance."""
        assert isinstance(settings, Settings)

    def test_database_settings(self):
        """Test database configuration."""
        s = Settings()

        assert s.DATABASE_URL == "postgresql://postgres:postgres@localhost:5432/penelle_test"
        assert s.database_url == s.DATABASE_URL
        assert (
            s.ASYNC_DATABASE_URL
            == "postgresql+asyncpg://postgres:postgres@localhost:5432/penelle_test"
        )
        assert s.async_database_url == s.ASYNC_DATABASE_URL
        assert s.DATABASE_POOL_SIZE == 10
        assert s.DATABASE_MAX_OVERFLOW == 20

    def test_redis_settings(self):
        """Test Redis configuration."""
        s = Settings()

        assert s.REDIS_URL == "redis://localhost:6379/0"
        assert s.redis_url == s.REDIS_URL

    def test_environment_settings(self):
        """Test environment configuration."""
        s = Settings()

        assert s.environment == "test"
        assert s.ENV == "test"

    def test_jwt_settings(self):
        """Test JWT configuration."""
        s = Settings()

        assert s.SECRET_KEY == "test-secret-key"
        assert s.JWT_SECRET_KEY == "test-jwt-secret"
        assert s.JWT_ALGORITHM == "HS256"
        assert s.ALGORITHM == "HS256"
        assert s.JWT_EXPIRATION_MINUTES == 30
        assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 30
        assert s.REFRESH_TOKEN_EXPIRE_DAYS == 7

    def test_s3_settings(self):
        """Test S3 configuration."""
        s = Settings()

        assert s.S3_BUCKET_NAME == "penelle-test"
        assert s.S3_ENDPOINT_URL == "http://localhost:9000"
        assert s.S3_ACCESS_KEY_ID == "minioadmin"
        assert s.S3_SECRET_ACCESS_KEY == "minioadmin"
        assert s.S3_REGION_NAME == "us-east-1"
        assert s.S3_USE_SSL is False
        assert s.S3_VERIFY_SSL is False
        assert s.S3_MAX_CONCURRENCY == 10
        assert 1024 * 1024 * 5 == s.S3_MULTIPART_THRESHOLD
        assert 1024 * 1024 == s.S3_MULTIPART_CHUNKSIZE
        assert s.S3_PRESIGNED_URL_EXPIRY == 3600

    def test_file_settings(self):
        """Test file handling configuration."""
        s = Settings()

        assert s.TEMP_DIR == "/tmp"
        assert s.FILE_CLEANUP_AGE == 3600
        assert 1024 * 1024 * 100 == s.MAX_FILE_SIZE
        assert 1024 * 1024 * 50 == s.MAX_UPLOAD_SIZE
        assert [".pdf", ".doc", ".docx", ".txt"] == s.ALLOWED_UPLOAD_EXTENSIONS

    def test_all_attributes_present(self):
        """Test that all expected attributes are present."""
        s = Settings()

        expected_attrs = [
            "DATABASE_URL",
            "database_url",
            "ASYNC_DATABASE_URL",
            "async_database_url",
            "REDIS_URL",
            "redis_url",
            "environment",
            "ENV",
            "DATABASE_POOL_SIZE",
            "DATABASE_MAX_OVERFLOW",
            "SECRET_KEY",
            "JWT_SECRET_KEY",
            "JWT_ALGORITHM",
            "ALGORITHM",
            "JWT_EXPIRATION_MINUTES",
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            "REFRESH_TOKEN_EXPIRE_DAYS",
            "S3_BUCKET_NAME",
            "S3_ENDPOINT_URL",
            "S3_ACCESS_KEY_ID",
            "S3_SECRET_ACCESS_KEY",
            "S3_REGION_NAME",
            "S3_USE_SSL",
            "S3_VERIFY_SSL",
            "S3_MAX_CONCURRENCY",
            "S3_MULTIPART_THRESHOLD",
            "S3_MULTIPART_CHUNKSIZE",
            "S3_PRESIGNED_URL_EXPIRY",
            "TEMP_DIR",
            "FILE_CLEANUP_AGE",
            "MAX_FILE_SIZE",
            "ALLOWED_UPLOAD_EXTENSIONS",
            "MAX_UPLOAD_SIZE",
        ]

        for attr in expected_attrs:
            assert hasattr(s, attr), f"Missing attribute: {attr}"

    def test_settings_are_consistent(self):
        """Test that uppercase and lowercase attributes are consistent."""
        s = Settings()

        assert s.database_url == s.DATABASE_URL
        assert s.async_database_url == s.ASYNC_DATABASE_URL
        assert s.redis_url == s.REDIS_URL
        assert s.JWT_ALGORITHM == s.ALGORITHM

    def test_multiple_instances_identical(self):
        """Test that multiple Settings instances have identical values."""
        s1 = Settings()
        s2 = Settings()

        assert s1.DATABASE_URL == s2.DATABASE_URL
        assert s1.JWT_SECRET_KEY == s2.JWT_SECRET_KEY
        assert s1.S3_BUCKET_NAME == s2.S3_BUCKET_NAME
        assert s1.ALLOWED_UPLOAD_EXTENSIONS == s2.ALLOWED_UPLOAD_EXTENSIONS
