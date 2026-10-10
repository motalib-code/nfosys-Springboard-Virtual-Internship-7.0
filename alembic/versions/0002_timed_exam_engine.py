"""add timed exam engine fields to exam_sessions

Revision ID: 0002_timed_exam_engine
Revises: 0001_initial
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_timed_exam_engine'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('exam_sessions', sa.Column('server_deadline', sa.DateTime(timezone=True), nullable=True))
    op.add_column('exam_sessions', sa.Column('submitted_reason', sa.Enum('manual', 'time_expired', 'proctor_terminated', 'admin_forced', name='submittedreason', native_enum=False), nullable=True))
    op.add_column('exam_sessions', sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_exam_sessions_server_deadline'), 'exam_sessions', ['server_deadline'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_exam_sessions_server_deadline'), table_name='exam_sessions')
    op.drop_column('exam_sessions', 'last_activity_at')
    op.drop_column('exam_sessions', 'submitted_reason')
    op.drop_column('exam_sessions', 'server_deadline')
