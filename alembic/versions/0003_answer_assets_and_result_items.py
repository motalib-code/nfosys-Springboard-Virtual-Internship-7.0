"""add answer thumbnail and result item audit table

Revision ID: 0003_answer_assets_and_result_items
Revises: 0002_timed_exam_engine
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '0003_answer_assets_and_result_items'
down_revision = '0002_timed_exam_engine'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('answers', sa.Column('thumbnail_url', sa.String(length=512), nullable=True))

    op.create_table(
        'result_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('result_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('question_id', sa.String(length=36), nullable=False),
        sa.Column('question_type', sa.Enum('MCQ', 'multi_select', 'short_answer', 'long_answer', 'image_upload', name='questiontype', native_enum=False), nullable=False),
        sa.Column('max_marks', sa.Float(), nullable=False),
        sa.Column('marks_awarded', sa.Float(), nullable=False),
        sa.Column('negative_deduction', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('scoring_strategy', sa.String(length=100), nullable=False),
        sa.Column('scoring_details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['question_id'], ['question_bank.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['result_id'], ['results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_result_items_result_id'), 'result_items', ['result_id'], unique=False)
    op.create_index(op.f('ix_result_items_session_id'), 'result_items', ['session_id'], unique=False)
    op.create_index(op.f('ix_result_items_question_id'), 'result_items', ['question_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_result_items_question_id'), table_name='result_items')
    op.drop_index(op.f('ix_result_items_session_id'), table_name='result_items')
    op.drop_index(op.f('ix_result_items_result_id'), table_name='result_items')
    op.drop_table('result_items')
    op.drop_column('answers', 'thumbnail_url')
