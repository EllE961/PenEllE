"""Seed default roles and permissions

Revision ID: 005
Revises: 004
Create Date: 2025-08-04 20:01:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Define tables for bulk insert
    roles_table = table('roles',
        column('id', postgresql.UUID(as_uuid=True)),
        column('name', sa.String),
        column('description', sa.Text),
        column('permissions', sa.JSON)
    )
    
    permissions_table = table('permissions',
        column('id', postgresql.UUID(as_uuid=True)),
        column('resource', sa.String),
        column('action', sa.String),
        column('description', sa.Text)
    )
    
    # Default roles data
    default_roles = [
        {
            'id': uuid4(),
            'name': 'owner',
            'description': 'Full tenant control - can do everything',
            'permissions': ['*:*']
        },
        {
            'id': uuid4(),
            'name': 'admin',
            'description': 'Manage users, roles, and templates - no document access',
            'permissions': [
                'users:*', 'roles:*', 'templates:*',
                'system:read', 'system:update'
            ]
        },
        {
            'id': uuid4(),
            'name': 'operator',
            'description': 'Manage pipeline operations - no document access',
            'permissions': [
                'runs:create', 'runs:read', 'runs:update', 'runs:execute',
                'system:read', 'templates:read'
            ]
        },
        {
            'id': uuid4(),
            'name': 'reviewer',
            'description': 'Read artifacts, comment, and approve',
            'permissions': [
                'runs:read', 'artifacts:read', 'artifacts:approve',
                'sources:read', 'evidence:read', 'claims:read',
                'quality:read', 'quality:approve'
            ]
        },
        {
            'id': uuid4(),
            'name': 'author',
            'description': 'Create runs and manage own artifacts',
            'permissions': [
                'runs:create', 'runs:read', 'runs:update', 'runs:delete',
                'artifacts:create', 'artifacts:read', 'artifacts:update',
                'sources:create', 'sources:read', 'evidence:create',
                'evidence:read', 'claims:create', 'claims:read',
                'templates:read'
            ]
        },
        {
            'id': uuid4(),
            'name': 'viewer',
            'description': 'Read-only access to public resources',
            'permissions': [
                'runs:read', 'artifacts:read', 'sources:read',
                'evidence:read', 'claims:read', 'quality:read',
                'templates:read'
            ]
        }
    ]
    
    # Insert default roles
    op.bulk_insert(roles_table, default_roles)
    
    # Default permissions data
    resources = [
        'runs', 'artifacts', 'users', 'roles', 'templates',
        'system', 'sources', 'evidence', 'claims', 'quality'
    ]
    actions = ['create', 'read', 'update', 'delete', 'execute', 'approve', 'admin']
    
    permissions = []
    for resource in resources:
        for action in actions:
            # Skip some invalid combinations
            if resource == 'system' and action in ['create', 'delete']:
                continue
            if resource == 'quality' and action not in ['read', 'approve']:
                continue
                
            permissions.append({
                'id': uuid4(),
                'resource': resource,
                'action': action,
                'description': f'{action.capitalize()} {resource}'
            })
    
    # Insert permissions
    op.bulk_insert(permissions_table, permissions)


def downgrade() -> None:
    # Delete seeded data
    op.execute("DELETE FROM user_roles")
    op.execute("DELETE FROM roles WHERE name IN ('owner', 'admin', 'operator', 'reviewer', 'author', 'viewer')")
    op.execute("DELETE FROM permissions")