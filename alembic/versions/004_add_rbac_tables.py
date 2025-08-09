"""Add RBAC tables

Revision ID: 004
Revises: 003
Create Date: 2025-08-04 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create roles table
    op.create_table('roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('permissions', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('idx_roles_name', 'roles', ['name'], unique=False)
    
    # Create permissions table
    op.create_table('permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('resource', 'action', name='uq_permission')
    )
    op.create_index('idx_permissions_resource_action', 'permissions', ['resource', 'action'], unique=False)
    
    # Create user_roles association table
    op.create_table('user_roles',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    op.create_index('idx_user_roles_role', 'user_roles', ['role_id'], unique=False)
    op.create_index('idx_user_roles_user', 'user_roles', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_user_roles_user', table_name='user_roles')
    op.drop_index('idx_user_roles_role', table_name='user_roles')
    op.drop_index('idx_permissions_resource_action', table_name='permissions')
    op.drop_index('idx_roles_name', table_name='roles')
    
    # Drop tables
    op.drop_table('user_roles')
    op.drop_table('permissions')
    op.drop_table('roles')