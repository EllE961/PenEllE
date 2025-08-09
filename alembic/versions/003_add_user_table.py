"""Add User table for authentication

Revision ID: 003
Revises: 002
Create Date: 2025-08-04 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('roles', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('organization', sa.String(length=255), nullable=True),
        sa.Column('preferences', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_users_active', 'users', ['is_active'], unique=False)
    op.create_index('idx_users_created', 'users', ['created_at'], unique=False)
    op.create_index('idx_users_email', 'users', ['email'], unique=True)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_users_email', table_name='users')
    op.drop_index('idx_users_created', table_name='users')
    op.drop_index('idx_users_active', table_name='users')
    
    # Drop table
    op.drop_table('users')