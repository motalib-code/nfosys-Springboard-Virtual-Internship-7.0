"""initial migration

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('student', 'examiner', 'admin', name='userrole', native_enum=False), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    # 2. question_bank
    op.create_table(
        'question_bank',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('question_type', sa.Enum('MCQ', 'multi_select', 'short_answer', 'long_answer', 'image_upload', name='questiontype', native_enum=False), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('difficulty', sa.Enum('easy', 'medium', 'hard', name='difficulty', native_enum=False), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('image_url', sa.String(length=512), nullable=True),
        sa.Column('marks', sa.Float(), nullable=False),
        sa.Column('negative_marks', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('model_answer', sa.Text(), nullable=True),
        sa.Column('expected_answer', sa.JSON(), nullable=True),
        sa.Column('max_marks_for_image', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('negative_marks >= 0', name='check_negative_marks_non_negative'),
        sa.CheckConstraint('negative_marks <= marks', name='check_negative_marks_lte_marks'),
        sa.CheckConstraint('marks > 0', name='check_marks_positive'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_question_bank_created_by'), 'question_bank', ['created_by'], unique=False)
    op.create_index(op.f('ix_question_bank_question_type'), 'question_bank', ['question_type'], unique=False)
    op.create_index(op.f('ix_question_bank_subject'), 'question_bank', ['subject'], unique=False)
    op.create_index(op.f('ix_question_bank_difficulty'), 'question_bank', ['difficulty'], unique=False)

    # 3. options
    op.create_table(
        'options',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('question_id', sa.String(length=36), nullable=False),
        sa.Column('option_text', sa.Text(), nullable=False),
        sa.Column('is_correct', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['question_id'], ['question_bank.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_options_question_id'), 'options', ['question_id'], unique=False)

    # 4. exams
    op.create_table(
        'exams',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('randomization_mode', sa.Enum('none', 'per_student_unique', name='randomizationmode', native_enum=False), nullable=False, server_default='none'),
        sa.Column('negative_marking_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('selection_rules', sa.JSON(), nullable=True),
        sa.Column('proctoring_settings', sa.JSON(), nullable=True),
        sa.Column('status', sa.Enum('draft', 'published', 'closed', name='examstatus', native_enum=False), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('end_time > start_time', name='check_end_time_after_start_time'),
        sa.CheckConstraint('duration_minutes > 0', name='check_duration_positive'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exams_created_by'), 'exams', ['created_by'], unique=False)
    op.create_index(op.f('ix_exams_subject'), 'exams', ['subject'], unique=False)
    op.create_index(op.f('ix_exams_status'), 'exams', ['status'], unique=False)

    # 5. exam_questions
    op.create_table(
        'exam_questions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('exam_id', sa.String(length=36), nullable=False),
        sa.Column('question_id', sa.String(length=36), nullable=False),
        sa.Column('marks_override', sa.Float(), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['question_bank.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'question_id', name='uq_exam_question')
    )
    op.create_index(op.f('ix_exam_questions_exam_id'), 'exam_questions', ['exam_id'], unique=False)
    op.create_index(op.f('ix_exam_questions_question_id'), 'exam_questions', ['question_id'], unique=False)

    # 6. exam_sessions
    op.create_table(
        'exam_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('exam_id', sa.String(length=36), nullable=False),
        sa.Column('student_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.Enum('not_started', 'in_progress', 'submitted', 'auto_submitted', 'flagged', 'terminated', name='sessionstatus', native_enum=False), nullable=False, server_default='not_started'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('active_token_jti', sa.String(length=255), nullable=True),
        sa.Column('client_ip', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('paper_seed', sa.String(length=255), nullable=True),
        sa.Column('generated_paper', sa.JSON(), nullable=True),
        sa.Column('tab_switch_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_flagged', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exam_id', 'student_id', name='uq_exam_student_session')
    )
    op.create_index(op.f('ix_exam_sessions_exam_id'), 'exam_sessions', ['exam_id'], unique=False)
    op.create_index(op.f('ix_exam_sessions_student_id'), 'exam_sessions', ['student_id'], unique=False)
    op.create_index(op.f('ix_exam_sessions_status'), 'exam_sessions', ['status'], unique=False)
    op.create_index(op.f('ix_exam_sessions_active_token_jti'), 'exam_sessions', ['active_token_jti'], unique=False)

    # 7. answers
    op.create_table(
        'answers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('question_id', sa.String(length=36), nullable=False),
        sa.Column('selected_option_ids', sa.JSON(), nullable=True),
        sa.Column('text_answer', sa.Text(), nullable=True),
        sa.Column('image_answer_url', sa.String(length=512), nullable=True),
        sa.Column('marks_awarded', sa.Float(), nullable=True),
        sa.Column('graded_by', sa.String(length=36), nullable=True),
        sa.Column('graded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['question_id'], ['question_bank.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['graded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'question_id', name='uq_session_question_answer')
    )
    op.create_index(op.f('ix_answers_session_id'), 'answers', ['session_id'], unique=False)
    op.create_index(op.f('ix_answers_question_id'), 'answers', ['question_id'], unique=False)

    # 8. results
    op.create_table(
        'results',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('total_marks', sa.Float(), nullable=False),
        sa.Column('obtained_marks', sa.Float(), nullable=False),
        sa.Column('negative_deductions', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('percentage', sa.Float(), nullable=False),
        sa.Column('grading_status', sa.Enum('pending', 'auto_graded', 'manually_graded', 'final', name='gradingstatus', native_enum=False), nullable=False, server_default='pending'),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_results_session_id'), 'results', ['session_id'], unique=True)
    op.create_index(op.f('ix_results_grading_status'), 'results', ['grading_status'], unique=False)

    # 9. proctor_events
    op.create_table(
        'proctor_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.Enum('webcam_snapshot', 'gaze_away', 'tab_switch', 'multiple_faces', 'no_face', 'window_blur', 'fullscreen_exit', name='proctoreventtype', native_enum=False), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('severity', sa.String(length=50), nullable=False, server_default='warning'),
        sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_proctor_events_session_id'), 'proctor_events', ['session_id'], unique=False)
    op.create_index(op.f('ix_proctor_events_event_type'), 'proctor_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_proctor_events_timestamp'), 'proctor_events', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_table('proctor_events')
    op.drop_table('results')
    op.drop_table('answers')
    op.drop_table('exam_sessions')
    op.drop_table('exam_questions')
    op.drop_table('exams')
    op.drop_table('options')
    op.drop_table('question_bank')
    op.drop_table('users')
