"""Configuration management for PenEllE."""

from typing import List, Optional

from pydantic import Field, PostgresDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Allow extra environment variables
    )

    # Application
    PROJECT_NAME: str = "PenEllE"
    VERSION: str = "0.1.0"
    DEBUG: bool = Field(default=False)

    # Database
    POSTGRES_USER: str = Field(default="penelle")
    POSTGRES_PASSWORD: str = Field(default="penelle")
    POSTGRES_SERVER: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="penelle")
    DATABASE_URL: Optional[str] = None
    ASYNC_DATABASE_URL: Optional[str] = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info: ValidationInfo) -> str:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql",
            username=info.data.get("POSTGRES_USER"),
            password=info.data.get("POSTGRES_PASSWORD"),
            host=info.data.get("POSTGRES_SERVER"),
            port=info.data.get("POSTGRES_PORT"),
            path=f"{info.data.get('POSTGRES_DB') or ''}",
        ).unicode_string()

    @field_validator("ASYNC_DATABASE_URL", mode="before")
    @classmethod
    def assemble_async_db_connection(cls, v: Optional[str], info: ValidationInfo) -> str:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=info.data.get("POSTGRES_USER"),
            password=info.data.get("POSTGRES_PASSWORD"),
            host=info.data.get("POSTGRES_SERVER"),
            port=info.data.get("POSTGRES_PORT"),
            path=f"{info.data.get('POSTGRES_DB') or ''}",
        ).unicode_string()

    # S3/MinIO
    S3_ENDPOINT_URL: Optional[str] = Field(default="http://localhost:9000")
    S3_ACCESS_KEY_ID: str = Field(default="minioadmin", alias="AWS_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: str = Field(default="minioadmin", alias="AWS_SECRET_ACCESS_KEY")
    S3_REGION_NAME: str = Field(default="us-east-1", alias="AWS_DEFAULT_REGION")
    S3_BUCKET_NAME: str = Field(default="penelle")
    S3_USE_SSL: bool = Field(default=False)
    S3_VERIFY_SSL: bool = Field(default=True)

    # S3 Upload settings
    S3_MULTIPART_THRESHOLD: int = Field(default=10 * 1024 * 1024)  # 10MB
    S3_MULTIPART_CHUNKSIZE: int = Field(default=10 * 1024 * 1024)  # 10MB
    S3_MAX_CONCURRENCY: int = Field(default=10)
    S3_PRESIGNED_URL_EXPIRY: int = Field(default=3600)  # 1 hour in seconds

    # Storage settings
    STORAGE_RETENTION_DAYS: int = Field(default=90)
    STORAGE_METRICS_RETENTION_DAYS: int = Field(default=365)

    # Redis
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_DB: int = Field(default=0)
    REDIS_PASSWORD: Optional[str] = Field(default=None)

    # JWT
    SECRET_KEY: str = Field(default="your-secret-key-here-change-in-production")
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)

    # Ollama
    OLLAMA_HOST: str = Field(default="http://localhost:11434")
    OLLAMA_MODEL: str = Field(default="llama2:13b")

    # OpenAI (optional)
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    OPENAI_MODEL: str = Field(default="gpt-4")

    # Anthropic (optional)
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None)
    ANTHROPIC_MODEL: str = Field(default="claude-3-opus-20240229")

    # File handling
    TEMP_DIR: str = Field(default="/tmp/penelle")
    MAX_FILE_SIZE: int = Field(default=100 * 1024 * 1024)  # 100MB
    MAX_UPLOAD_SIZE: int = Field(default=50 * 1024 * 1024)  # 50MB
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = Field(
        default=[".pdf", ".txt", ".md", ".docx", ".doc", ".rtf", ".tex", ".bib"]
    )
    ALLOWED_ARCHIVE_EXTENSIONS: List[str] = Field(default=[".zip", ".tar", ".tar.gz", ".tgz"])
    FILE_CLEANUP_INTERVAL: int = Field(default=3600)  # 1 hour in seconds
    FILE_CLEANUP_AGE: int = Field(default=86400)  # 24 hours in seconds

    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")

    # Tracing
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(default=None)
    OTEL_SERVICE_NAME: str = Field(default="penelle")
    ENABLE_TRACING: bool = Field(default=False)


# Create global settings instance
settings = Settings()
