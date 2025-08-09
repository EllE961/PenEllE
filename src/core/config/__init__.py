"""Configuration module for PenEllE."""

from .loader import ConfigLoader, get_config_loader, load_config
from .models import (
    ConnectorConfig,
    ConnectorType,
    DeploymentConfig,
    Environment,
    ModelConfig,
    OutputFormat,
    PipelineConfig,
    ProviderType,
    QualityGateConfig,
    load_connector_config,
    load_deployment_config,
    load_model_config,
    load_pipeline_config,
    load_quality_gates,
)

__all__ = [
    "ConfigLoader",
    "get_config_loader",
    "load_config",
    "ModelConfig",
    "ConnectorConfig",
    "QualityGateConfig",
    "DeploymentConfig",
    "PipelineConfig",
    "ProviderType",
    "ConnectorType",
    "OutputFormat",
    "Environment",
    "load_model_config",
    "load_connector_config",
    "load_quality_gates",
    "load_deployment_config",
    "load_pipeline_config",
    "settings",
]


# Create a settings object for compatibility
class Settings:
    """Settings object for database and other configurations."""

    def __init__(self) -> None:
        self.DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/penelle_test"
        self.database_url = self.DATABASE_URL
        self.ASYNC_DATABASE_URL = (
            "postgresql+asyncpg://postgres:postgres@localhost:5432/penelle_test"
        )
        self.async_database_url = self.ASYNC_DATABASE_URL
        self.REDIS_URL = "redis://localhost:6379/0"
        self.redis_url = self.REDIS_URL
        self.environment = "test"
        self.ENV = "test"
        self.DATABASE_POOL_SIZE = 10
        self.DATABASE_MAX_OVERFLOW = 20
        self.SECRET_KEY = "test-secret-key"
        self.JWT_SECRET_KEY = "test-jwt-secret"
        self.JWT_ALGORITHM = "HS256"
        self.ALGORITHM = "HS256"  # Alias for compatibility
        self.JWT_EXPIRATION_MINUTES = 30
        self.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        self.REFRESH_TOKEN_EXPIRE_DAYS = 7

        # S3 settings
        self.S3_BUCKET_NAME = "penelle-test"
        self.S3_ENDPOINT_URL = "http://localhost:9000"
        self.S3_ACCESS_KEY_ID = "minioadmin"
        self.S3_SECRET_ACCESS_KEY = "minioadmin"
        self.S3_REGION_NAME = "us-east-1"
        self.S3_USE_SSL = False
        self.S3_VERIFY_SSL = False
        self.S3_MAX_CONCURRENCY = 10
        self.S3_MULTIPART_THRESHOLD = 1024 * 1024 * 5
        self.S3_MULTIPART_CHUNKSIZE = 1024 * 1024
        self.S3_PRESIGNED_URL_EXPIRY = 3600

        # File settings
        self.TEMP_DIR = "/tmp"
        self.FILE_CLEANUP_AGE = 3600
        self.MAX_FILE_SIZE = 1024 * 1024 * 100
        self.ALLOWED_UPLOAD_EXTENSIONS = [".pdf", ".doc", ".docx", ".txt"]
        self.MAX_UPLOAD_SIZE = 1024 * 1024 * 50


settings = Settings()
