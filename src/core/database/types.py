"""Custom database types for cross-database compatibility."""

import uuid
from typing import Any

from sqlalchemy import CHAR, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class UUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type when available, otherwise uses CHAR(36).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        """Load the appropriate implementation for the dialect."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        """Process UUID value for database binding."""
        if value is None:
            return value

        if dialect.name == "postgresql":
            return value
        else:
            # For SQLite and other databases, convert UUID to string
            if isinstance(value, uuid.UUID):
                return str(value)
            return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Process database value to UUID."""
        if value is None:
            return value

        if dialect.name == "postgresql":
            return value
        else:
            # For SQLite and other databases, convert string to UUID
            if isinstance(value, str):
                return uuid.UUID(value)
            else:
                return value
