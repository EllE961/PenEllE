"""Add pgvector extension and embeddings tables

Revision ID: 003_add_pgvector_embeddings
Revises: 002_add_event_logs
Create Date: 2025-08-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Create pgvector extension and embedding tables."""
    # Create pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create embeddings table
    op.create_table(
        'embeddings',
        sa.Column('embedding_id', postgresql.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('content_id', postgresql.UUID(), nullable=False),
        sa.Column('content_type', sa.String(50), nullable=False),
        sa.Column('collection', sa.String(50), nullable=False),
        sa.Column('embedding', Vector(1024), nullable=False),  # Max dimension size
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('dimensions', sa.Integer(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('embedding_id')
    )
    
    # Create indices
    op.create_index('idx_embeddings_content', 'embeddings', ['content_id', 'content_type'])
    op.create_index('idx_embeddings_collection', 'embeddings', ['collection'])
    op.create_index('idx_embeddings_model', 'embeddings', ['model_name'])
    
    # Create vector indices for each expected dimension size
    # We'll create these dynamically based on actual usage, but here are common ones
    op.execute("""
        CREATE INDEX idx_embeddings_vector_384 ON embeddings 
        USING ivfflat ((embedding::vector(384)) vector_cosine_ops)
        WHERE dimensions = 384;
    """)
    
    op.execute("""
        CREATE INDEX idx_embeddings_vector_768 ON embeddings 
        USING ivfflat ((embedding::vector(768)) vector_cosine_ops)
        WHERE dimensions = 768;
    """)
    
    op.execute("""
        CREATE INDEX idx_embeddings_vector_1024 ON embeddings 
        USING ivfflat ((embedding::vector(1024)) vector_cosine_ops)
        WHERE dimensions = 1024;
    """)
    
    # Create search history table for analytics
    op.create_table(
        'search_history',
        sa.Column('search_id', postgresql.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('run_id', postgresql.UUID(), nullable=True),
        sa.Column('user_id', postgresql.UUID(), nullable=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('query_embedding', Vector(1024), nullable=True),
        sa.Column('search_type', sa.String(50), nullable=False),  # semantic, hybrid, keyword
        sa.Column('collection', sa.String(50), nullable=False),
        sa.Column('filters', postgresql.JSONB(), nullable=True),
        sa.Column('results_count', sa.Integer(), nullable=False),
        sa.Column('top_score', sa.Float(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('search_id')
    )
    
    op.create_index('idx_search_history_run', 'search_history', ['run_id'])
    op.create_index('idx_search_history_user', 'search_history', ['user_id'])
    op.create_index('idx_search_history_created', 'search_history', ['created_at'])
    
    # Note: Foreign key constraints to 'runs' and 'users' tables are not created
    # as these tables may not exist yet. They can be added in a future migration
    # when those tables are created.


def downgrade():
    """Drop pgvector tables and extension."""
    # Drop tables
    op.drop_table('search_history')
    op.drop_table('embeddings')
    
    # Drop extension
    op.execute('DROP EXTENSION IF EXISTS vector')