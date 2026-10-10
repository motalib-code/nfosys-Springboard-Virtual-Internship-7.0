"""week 3 and 4 database schema updates

Revision ID: 0003_week3_4_tables
Revises: 0002_timed_exam_engine
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_week3_4_tables'
down_revision = '0002_timed_exam_engine'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update exam_sessions table
    op.add_column('exam_sessions', sa.Column('suspicion_score', sa.Float(), nullable=False, server_default='0.0'))

    # 2. Update answers table
    op.add_column('answers', sa.Column('thumbnail_url', sa.String(length=512), nullable=True))

    # 3. Create ai_evaluations table
    op.create_table(
        'ai_evaluations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('answer_id', sa.String(length=36), nullable=False),
        sa.Column('model_name', sa.String(length=255), nullable=False),
        sa.Column('prompt_version', sa.String(length=50), nullable=False),
        sa.Column('suggested_score', sa.Float(), nullable=False),
        sa.Column('max_score', sa.Float(), nullable=False),
        sa.Column('justification', sa.Text(), nullable=False),
        sa.Column('key_points_matched', sa.JSON(), nullable=True),
        sa.Column('key_points_missed', sa.JSON(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('ocr_text', sa.Text(), nullable=True),
        sa.Column('ocr_confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='completed'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('token_usage', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['answer_id'], ['answers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_evaluations_answer_id'), 'ai_evaluations', ['answer_id'], unique=False)

    # 4. Create grading_queue table
    op.create_table(
        'grading_queue',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('answer_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('exam_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.Enum('pending', 'processing_ai', 'ready_for_review', 'in_review', 'graded', 'failed', name='gradingqueuestatus', native_enum=False), nullable=False, server_default='pending'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('claimed_by', sa.String(length=255), nullable=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['answer_id'], ['answers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_grading_queue_answer_id'), 'grading_queue', ['answer_id'], unique=True)
    op.create_index(op.f('ix_grading_queue_exam_id'), 'grading_queue', ['exam_id'], unique=False)
    op.create_index(op.f('ix_grading_queue_session_id'), 'grading_queue', ['session_id'], unique=False)
    op.create_index(op.f('ix_grading_queue_status'), 'grading_queue', ['status'], unique=False)
    op.create_index('ix_grading_queue_exam_status_created_id', 'grading_queue', ['exam_id', 'status', 'created_at', 'id'], unique=False)

    # 5. Create grading_audit_log table
    op.create_table(
        'grading_audit_log',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('answer_id', sa.String(length=36), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('old_score', sa.Float(), nullable=True),
        sa.Column('new_score', sa.Float(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['answer_id'], ['answers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_grading_audit_log_actor_id'), 'grading_audit_log', ['actor_id'], unique=False)
    op.create_index(op.f('ix_grading_audit_log_answer_id'), 'grading_audit_log', ['answer_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_grading_audit_log_answer_id'), table_name='grading_audit_log')
    op.drop_index(op.f('ix_grading_audit_log_actor_id'), table_name='grading_audit_log')
    op.drop_table('grading_audit_log')

    op.drop_index('ix_grading_queue_exam_status_created_id', table_name='grading_queue')
    op.drop_index(op.f('ix_grading_queue_status'), table_name='grading_queue')
    op.drop_index(op.f('ix_grading_queue_session_id'), table_name='grading_queue')
    op.drop_index(op.f('ix_grading_queue_exam_id'), table_name='grading_queue')
    op.drop_index(op.f('ix_grading_queue_answer_id'), table_name='grading_queue')
    op.drop_table('grading_queue')

    op.drop_index(op.f('ix_ai_evaluations_answer_id'), table_name='ai_evaluations')
    op.drop_table('ai_evaluations')

    op.drop_column('answers', 'thumbnail_url')
    op.drop_column('exam_sessions', 'suspicion_score')
