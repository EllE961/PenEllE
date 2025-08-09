"""Tests for src/core/config.py module directly."""

# Now import the actual pydantic Settings by importing the module directly
import importlib.util
import os
from unittest.mock import patch

# Import directly from the config.py file to test it

spec = importlib.util.spec_from_file_location("config_py", "src/core/config.py")
config_py = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_py)

PydanticSettings = config_py.Settings


class TestCoreConfigPy:
    """Test cases for core/config.py Settings."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = PydanticSettings()

        # Application settings
        assert settings.PROJECT_NAME == "PenEllE"
        assert settings.VERSION == "0.1.0"
        # DEBUG can be True or False depending on environment
        assert isinstance(settings.DEBUG, bool)

        # Database settings
        assert settings.POSTGRES_USER == "penelle"
        assert settings.POSTGRES_PASSWORD == "penelle"
        assert settings.POSTGRES_SERVER == "localhost"
        assert settings.POSTGRES_PORT == 5432
        assert settings.POSTGRES_DB == "penelle"

    def test_database_url_assembly(self):
        """Test database URL assembly."""
        settings = PydanticSettings()

        # Should assemble from parts
        expected = "postgresql://penelle:penelle@localhost:5432/penelle"
        assert expected == settings.DATABASE_URL

        expected_async = "postgresql+asyncpg://penelle:penelle@localhost:5432/penelle"
        assert expected_async == settings.ASYNC_DATABASE_URL

    def test_s3_settings(self):
        """Test S3 settings."""
        settings = PydanticSettings()

        assert settings.S3_ENDPOINT_URL == "http://localhost:9000"
        assert settings.S3_ACCESS_KEY_ID == "minioadmin"
        assert settings.S3_SECRET_ACCESS_KEY == "minioadmin"
        assert settings.S3_BUCKET_NAME == "penelle"
        assert settings.S3_USE_SSL is False
        assert settings.S3_VERIFY_SSL is True
        assert 10 * 1024 * 1024 == settings.S3_MULTIPART_THRESHOLD
        assert settings.S3_MAX_CONCURRENCY == 10

    def test_redis_settings(self):
        """Test Redis settings."""
        settings = PydanticSettings()

        assert settings.REDIS_HOST == "localhost"
        assert settings.REDIS_PORT == 6379
        assert settings.REDIS_DB == 0
        assert settings.REDIS_PASSWORD is None

    def test_jwt_settings(self):
        """Test JWT settings."""
        settings = PydanticSettings()

        # SECRET_KEY can vary based on environment
        assert isinstance(settings.SECRET_KEY, str)
        assert settings.ALGORITHM == "HS256"
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30
        assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7

    def test_file_settings(self):
        """Test file handling settings."""
        settings = PydanticSettings()

        assert settings.TEMP_DIR == "/tmp/penelle"
        assert 100 * 1024 * 1024 == settings.MAX_FILE_SIZE
        assert 50 * 1024 * 1024 == settings.MAX_UPLOAD_SIZE
        assert ".pdf" in settings.ALLOWED_UPLOAD_EXTENSIONS
        assert ".zip" in settings.ALLOWED_ARCHIVE_EXTENSIONS
        assert settings.FILE_CLEANUP_INTERVAL == 3600
        assert settings.FILE_CLEANUP_AGE == 86400

    def test_llm_settings(self):
        """Test LLM settings."""
        settings = PydanticSettings()

        assert settings.OLLAMA_HOST == "http://localhost:11434"
        assert settings.OLLAMA_MODEL == "llama2:13b"
        # API keys can be None or empty string based on environment
        assert settings.OPENAI_API_KEY in (None, "")
        assert settings.OPENAI_MODEL == "gpt-4"
        assert settings.ANTHROPIC_API_KEY in (None, "")
        assert settings.ANTHROPIC_MODEL == "claude-3-opus-20240229"

    def test_other_settings(self):
        """Test other settings."""
        settings = PydanticSettings()

        assert settings.LOG_LEVEL == "INFO"
        assert settings.LOG_FORMAT == "json"
        assert settings.STORAGE_RETENTION_DAYS == 90
        assert settings.STORAGE_METRICS_RETENTION_DAYS == 365
        # OTEL_EXPORTER_OTLP_ENDPOINT can be None or a string based on environment
        assert settings.OTEL_EXPORTER_OTLP_ENDPOINT is None or isinstance(
            settings.OTEL_EXPORTER_OTLP_ENDPOINT, str
        )
        assert settings.OTEL_SERVICE_NAME == "penelle"
        assert settings.ENABLE_TRACING is False

    def test_env_override(self):
        """Test environment variable override."""
        with patch.dict(os.environ, {"DEBUG": "true", "LOG_LEVEL": "DEBUG"}):
            settings = PydanticSettings()
            assert settings.DEBUG is True
            assert settings.LOG_LEVEL == "DEBUG"

    def test_env_values_when_present(self):
        """Test that environment variables are loaded when present."""
        env_vars = {
            "DEBUG": "true",
            "SECRET_KEY": "your-app-secret-key-change-in-production",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }

        with patch.dict(os.environ, env_vars):
            settings = PydanticSettings()
            assert settings.DEBUG is True
            assert settings.SECRET_KEY == "your-app-secret-key-change-in-production"
            assert settings.OPENAI_API_KEY == ""
            assert settings.ANTHROPIC_API_KEY == ""
            assert settings.OTEL_EXPORTER_OTLP_ENDPOINT == "http://localhost:4317"

    def test_database_url_override(self):
        """Test DATABASE_URL can be overridden."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@host:5432/db"}):
            settings = PydanticSettings()
            assert settings.DATABASE_URL == "postgresql://user:pass@host:5432/db"

    def test_async_database_url_override(self):
        """Test ASYNC_DATABASE_URL can be overridden."""
        with patch.dict(
            os.environ, {"ASYNC_DATABASE_URL": "postgresql+asyncpg://user:pass@host:5432/db"}
        ):
            settings = PydanticSettings()
            assert settings.ASYNC_DATABASE_URL == "postgresql+asyncpg://user:pass@host:5432/db"

    def test_s3_aliases(self):
        """Test S3 settings with AWS aliases."""
        env_vars = {
            "AWS_ACCESS_KEY_ID": "test-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret",
            "AWS_DEFAULT_REGION": "eu-west-1",
        }

        with patch.dict(os.environ, env_vars):
            settings = PydanticSettings()
            assert settings.S3_ACCESS_KEY_ID == "test-key"
            assert settings.S3_SECRET_ACCESS_KEY == "test-secret"
            assert settings.S3_REGION_NAME == "eu-west-1"

    def test_model_config(self):
        """Test model configuration."""
        assert hasattr(PydanticSettings, "model_config")
        config = PydanticSettings.model_config
        assert config["env_file"] == ".env"
        assert config["env_file_encoding"] == "utf-8"
        assert config["case_sensitive"] is False
        assert config["extra"] == "ignore"

    def test_global_instance(self):
        """Test global settings instance exists."""
        assert hasattr(config_py, "settings")
        assert isinstance(config_py.settings, PydanticSettings)

    def test_field_types(self):
        """Test field types are correct."""
        settings = PydanticSettings()

        # Booleans
        assert isinstance(settings.DEBUG, bool)
        assert isinstance(settings.S3_USE_SSL, bool)
        assert isinstance(settings.ENABLE_TRACING, bool)

        # Integers
        assert isinstance(settings.POSTGRES_PORT, int)
        assert isinstance(settings.REDIS_PORT, int)
        assert isinstance(settings.MAX_FILE_SIZE, int)

        # Strings
        assert isinstance(settings.PROJECT_NAME, str)
        assert isinstance(settings.POSTGRES_USER, str)
        assert isinstance(settings.LOG_LEVEL, str)

        # Lists
        assert isinstance(settings.ALLOWED_UPLOAD_EXTENSIONS, list)
        assert isinstance(settings.ALLOWED_ARCHIVE_EXTENSIONS, list)
