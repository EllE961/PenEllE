"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2025-08-04 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial schema."""
    # Initial schema will be created by SQLAlchemy models
    pass


def downgrade() -> None:
    """Drop initial schema."""
    # Would drop all tables here
    pass