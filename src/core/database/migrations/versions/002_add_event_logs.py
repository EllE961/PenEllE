"""Add event logs table

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 12:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create event_logs table."""
    op.create_table(
        'event_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_id', sa.String(36), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('run_id', sa.String(36), nullable=False),
        sa.Column('stage', sa.String(20), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_event_logs_event_id', 'event_logs', ['event_id'])
    op.create_index('idx_event_logs_event_type', 'event_logs', ['event_type'])
    op.create_index('idx_event_logs_run_id', 'event_logs', ['run_id'])
    op.create_index('idx_event_logs_stage', 'event_logs', ['stage'])
    op.create_index('idx_event_logs_timestamp', 'event_logs', ['timestamp'])
    op.create_index('idx_event_logs_run_id_timestamp', 'event_logs', ['run_id', 'timestamp'])
    op.create_index('idx_event_logs_event_type_timestamp', 'event_logs', ['event_type', 'timestamp'])


def downgrade() -> None:
    """Drop event_logs table."""
    op.drop_index('idx_event_logs_event_type_timestamp', table_name='event_logs')
    op.drop_index('idx_event_logs_run_id_timestamp', table_name='event_logs')
    op.drop_index('idx_event_logs_timestamp', table_name='event_logs')
    op.drop_index('idx_event_logs_stage', table_name='event_logs')
    op.drop_index('idx_event_logs_run_id', table_name='event_logs')
    op.drop_index('idx_event_logs_event_type', table_name='event_logs')
    op.drop_index('idx_event_logs_event_id', table_name='event_logs')
    op.drop_table('event_logs')