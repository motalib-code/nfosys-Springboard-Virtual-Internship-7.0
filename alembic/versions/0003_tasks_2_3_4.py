"""add tasks 2 3 4 fields (suspicion_score, thumbnail_url, score_breakdown)

Revision ID: 0003_tasks_2_3_4
Revises: 0002_timed_exam_engine
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_tasks_2_3_4'
down_revision = '0002_timed_exam_engine'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('exam_sessions', sa.Column('suspicion_score', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('answers', sa.Column('thumbnail_url', sa.String(length=512), nullable=True))
    op.add_column('results', sa.Column('score_breakdown', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('results', 'score_breakdown')
    op.drop_column('answers', 'thumbnail_url')
    op.drop_column('exam_sessions', 'suspicion_score')
