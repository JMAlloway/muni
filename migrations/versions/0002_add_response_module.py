"""Add response module tables

Revision ID: 0002
Revises: 0001
Create Date: 2024-12-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create company_content_library table
    op.create_table(
        'company_content_library',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('team_id', sa.String(), nullable=True),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('data', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('attachments', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('searchable_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('keywords', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('wins_when_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_company_content_library_user_id', 'company_content_library', ['user_id'])
    op.create_index('ix_company_content_library_team_id', 'company_content_library', ['team_id'])
    op.create_index('ix_company_content_library_content_type', 'company_content_library', ['content_type'])
    op.create_index('ix_company_content_library_title', 'company_content_library', ['title'])

    # Create response_templates table
    op.create_table(
        'response_templates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('team_id', sa.String(), nullable=True),
        sa.Column('is_system_template', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('subcategory', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('keywords', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('question_patterns', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('agency_specific', sa.String(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('variables', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('required_attachments', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('trained_on', sa.String(), nullable=True),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('wins_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('losses_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_score', sa.Float(), nullable=True),
        sa.Column('avg_user_rating', sa.Float(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('previous_version_id', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_featured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_used', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_response_templates_user_id', 'response_templates', ['user_id'])
    op.create_index('ix_response_templates_team_id', 'response_templates', ['team_id'])
    op.create_index('ix_response_templates_title', 'response_templates', ['title'])
    op.create_index('ix_response_templates_category', 'response_templates', ['category'])
    op.create_index('ix_response_templates_agency_specific', 'response_templates', ['agency_specific'])

    # Create rfp_responses table
    op.create_table(
        'rfp_responses',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('opportunity_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('team_id', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('rfp_number', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='draft'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('sections', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('requirements', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('compliance_score', sa.Float(), nullable=True),
        sa.Column('requirements_met', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('requirements_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('missing_requirements', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('collaborators', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('comments_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('exports', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('submitted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('due_date', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('result', sa.String(), nullable=True),
        sa.Column('result_date', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('contract_value', sa.Float(), nullable=True),
        sa.Column('result_notes', sa.Text(), nullable=True),
        sa.Column('evaluation_score', sa.Float(), nullable=True),
        sa.Column('user_satisfaction', sa.Integer(), nullable=True),
        sa.Column('time_saved_hours', sa.Float(), nullable=True),
        sa.Column('would_use_again', sa.Boolean(), nullable=True),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rfp_responses_opportunity_id', 'rfp_responses', ['opportunity_id'])
    op.create_index('ix_rfp_responses_user_id', 'rfp_responses', ['user_id'])
    op.create_index('ix_rfp_responses_team_id', 'rfp_responses', ['team_id'])
    op.create_index('ix_rfp_responses_status', 'rfp_responses', ['status'])
    op.create_index('ix_rfp_responses_result', 'rfp_responses', ['result'])

    # Create response_questions table
    op.create_table(
        'response_questions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('rfp_response_id', sa.String(), nullable=False),
        sa.Column('question_number', sa.String(), nullable=True),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('section', sa.String(), nullable=True),
        sa.Column('question_type', sa.String(), nullable=False),
        sa.Column('keywords', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('page_limit', sa.String(), nullable=True),
        sa.Column('word_limit', sa.Integer(), nullable=True),
        sa.Column('requires_attachment', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('points_possible', sa.Integer(), nullable=True),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('page_count', sa.Float(), nullable=True),
        sa.Column('matched_template_id', sa.String(), nullable=True),
        sa.Column('match_confidence', sa.Float(), nullable=True),
        sa.Column('ai_generated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('ai_suggested_answer', sa.Text(), nullable=True),
        sa.Column('user_edited', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('edit_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('regeneration_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attachments', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('assigned_to', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_response_questions_rfp_response_id', 'response_questions', ['rfp_response_id'])
    op.create_index('ix_response_questions_question_type', 'response_questions', ['question_type'])
    op.create_index('ix_response_questions_matched_template_id', 'response_questions', ['matched_template_id'])

    # Create response_comments table
    op.create_table(
        'response_comments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('rfp_response_id', sa.String(), nullable=False),
        sa.Column('question_id', sa.String(), nullable=True),
        sa.Column('author_user_id', sa.String(), nullable=False),
        sa.Column('comment_text', sa.Text(), nullable=False),
        sa.Column('comment_type', sa.String(), nullable=False, server_default='general'),
        sa.Column('mentions', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_by', sa.String(), nullable=True),
        sa.Column('resolved_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_response_comments_rfp_response_id', 'response_comments', ['rfp_response_id'])
    op.create_index('ix_response_comments_question_id', 'response_comments', ['question_id'])
    op.create_index('ix_response_comments_author_user_id', 'response_comments', ['author_user_id'])

    # Create response_feedback table
    op.create_table(
        'response_feedback',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('rfp_response_id', sa.String(), nullable=False),
        sa.Column('question_id', sa.String(), nullable=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('template_used', sa.String(), nullable=True),
        sa.Column('ai_response', sa.Text(), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('user_response', sa.Text(), nullable=True),
        sa.Column('edit_distance', sa.Integer(), nullable=True),
        sa.Column('sections_regenerated', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('time_to_first_edit', sa.Integer(), nullable=True),
        sa.Column('time_spent_editing', sa.Integer(), nullable=True),
        sa.Column('user_rating', sa.Integer(), nullable=True),
        sa.Column('was_helpful', sa.Boolean(), nullable=True),
        sa.Column('user_accepted_as_is', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('user_deleted_and_rewrote', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('rfp_result', sa.String(), nullable=True),
        sa.Column('rfp_result_date', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('should_reinforce', sa.Boolean(), nullable=True),
        sa.Column('should_improve', sa.Boolean(), nullable=True),
        sa.Column('improvement_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_response_feedback_rfp_response_id', 'response_feedback', ['rfp_response_id'])
    op.create_index('ix_response_feedback_question_id', 'response_feedback', ['question_id'])
    op.create_index('ix_response_feedback_user_id', 'response_feedback', ['user_id'])
    op.create_index('ix_response_feedback_template_used', 'response_feedback', ['template_used'])
    op.create_index('ix_response_feedback_rfp_result', 'response_feedback', ['rfp_result'])


def downgrade() -> None:
    op.drop_table('response_feedback')
    op.drop_table('response_comments')
    op.drop_table('response_questions')
    op.drop_table('rfp_responses')
    op.drop_table('response_templates')
    op.drop_table('company_content_library')
