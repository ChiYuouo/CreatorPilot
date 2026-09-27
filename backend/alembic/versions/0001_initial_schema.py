"""为新数据库初始化完整的 CreatorPilot 表结构。

此云端基线替代开发阶段的 0001 至 0019 迁移。
它有意独立于原项目的迁移历史。
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('email', sa.VARCHAR(length=255), nullable=False),
        sa.Column('hashed_password', sa.VARCHAR(length=255), nullable=False),
        sa.Column('nickname', sa.VARCHAR(length=64), nullable=False),
        sa.Column('is_active', sa.BOOLEAN(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='users_pkey'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_table('analytics_reports',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('scope', sa.VARCHAR(length=32), nullable=False),
        sa.Column('title', sa.VARCHAR(length=255), nullable=False),
        sa.Column('content_id', sa.INTEGER(), nullable=True),
        sa.Column('report', sa.TEXT(), nullable=False),
        sa.Column('input_snapshot', sa.TEXT(), nullable=False),
        sa.Column('content_count', sa.INTEGER(), nullable=False),
        sa.Column('excluded_without_metrics', sa.INTEGER(), nullable=False),
        sa.Column('without_metrics_count', sa.INTEGER(), nullable=False),
        sa.Column('days', sa.INTEGER(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='analytics_reports_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='analytics_reports_pkey')
    )
    op.create_index('ix_analytics_reports_user_id', 'analytics_reports', ['user_id'], unique=False)
    op.create_table('automation_tasks',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('frequency', sa.VARCHAR(length=16), nullable=False),
        sa.Column('weekday', sa.INTEGER(), nullable=False),
        sa.Column('hour', sa.INTEGER(), nullable=False),
        sa.Column('minute', sa.INTEGER(), nullable=False),
        sa.Column('timezone', sa.VARCHAR(length=64), nullable=False),
        sa.Column('enabled', sa.BOOLEAN(), nullable=False),
        sa.Column('next_run_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('task_type', sa.VARCHAR(length=32), nullable=False),
        sa.Column('name', sa.VARCHAR(length=100), nullable=False),
        sa.Column('payload', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='report_schedules_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='report_schedules_pkey'),
    )
    op.create_index('ix_automation_tasks_user_id', 'automation_tasks', ['user_id'], unique=False)
    op.create_table('media_assets',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('filename', sa.VARCHAR(length=255), nullable=False),
        sa.Column('storage_path', sa.TEXT(), nullable=False),
        sa.Column('size_bytes', sa.INTEGER(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('media_type', sa.VARCHAR(length=16), server_default=sa.text("'video'::character varying"), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='media_assets_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='media_assets_pkey')
    )
    op.create_index('ix_media_assets_user_id', 'media_assets', ['user_id'], unique=False)
    op.create_table('platform_accounts',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('platform', sa.VARCHAR(length=32), nullable=False),
        sa.Column('account_name', sa.VARCHAR(length=100), nullable=False),
        sa.Column('status', sa.VARCHAR(length=20), nullable=False),
        sa.Column('checked_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('remark', sa.VARCHAR(length=100), nullable=True),
        sa.Column('is_deleted', sa.BOOLEAN(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='platform_accounts_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='platform_accounts_pkey'),
        sa.UniqueConstraint('platform', 'account_name', name='uq_platform_account_name'),
    )
    op.create_index('ix_platform_accounts_user_id', 'platform_accounts', ['user_id'], unique=False)
    op.create_table('automation_runs',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.INTEGER(), nullable=True),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('scheduled_for', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('status', sa.VARCHAR(length=16), nullable=False),
        sa.Column('error_message', sa.VARCHAR(length=500), nullable=True),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('finished_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('task_type', sa.VARCHAR(length=32), nullable=False),
        sa.Column('task_name', sa.VARCHAR(length=100), nullable=False),
        sa.Column('payload', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('result', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['automation_tasks.id'], name='report_runs_schedule_id_fkey', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='report_runs_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='report_runs_pkey'),
        sa.UniqueConstraint('task_id', 'scheduled_for', name='uq_automation_run_task_time'),
    )
    op.create_index('ix_automation_runs_task_id', 'automation_runs', ['task_id'], unique=False)
    op.create_index('ix_automation_runs_user_id', 'automation_runs', ['user_id'], unique=False)
    op.create_table('publish_plans',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('asset_id', sa.INTEGER(), nullable=False),
        sa.Column('title', sa.VARCHAR(length=255), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=False),
        sa.Column('tags_json', sa.TEXT(), nullable=False),
        sa.Column('scheduled_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('image_asset_ids_json', sa.TEXT(), server_default=sa.text("'[]'::text"), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['media_assets.id'], name='publish_plans_asset_id_fkey'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='publish_plans_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='publish_plans_pkey')
    )
    op.create_index('ix_publish_plans_user_id', 'publish_plans', ['user_id'], unique=False)
    op.create_table('published_contents',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('platform', sa.VARCHAR(length=32), nullable=False),
        sa.Column('title', sa.VARCHAR(length=255), nullable=False),
        sa.Column('published_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('account_id', sa.INTEGER(), nullable=True),
        sa.Column('platform_content_id', sa.VARCHAR(length=100), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['platform_accounts.id'], name='fk_published_account'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='published_contents_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='published_contents_pkey'),
        sa.UniqueConstraint('account_id', 'platform_content_id', name='uq_account_platform_content')
    )
    op.create_index('ix_published_contents_account_id', 'published_contents', ['account_id'], unique=False)
    op.create_index('ix_published_contents_user_id', 'published_contents', ['user_id'], unique=False)
    op.create_table('content_metrics',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('content_id', sa.INTEGER(), nullable=False),
        sa.Column('metric_date', sa.DATE(), nullable=False),
        sa.Column('views', sa.INTEGER(), nullable=True),
        sa.Column('likes', sa.INTEGER(), nullable=True),
        sa.Column('comments', sa.INTEGER(), nullable=True),
        sa.Column('favorites', sa.INTEGER(), nullable=True),
        sa.Column('shares', sa.INTEGER(), nullable=True),
        sa.Column('follower_gain', sa.INTEGER(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('source', sa.VARCHAR(length=32), nullable=False),
        sa.Column('collected_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('platform_updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['content_id'], ['published_contents.id'], name='content_metrics_content_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='content_metrics_pkey'),
        sa.UniqueConstraint('content_id', 'metric_date', name='uq_content_metric_date')
    )
    op.create_index('ix_content_metrics_content_id', 'content_metrics', ['content_id'], unique=False)
    op.create_table('metrics_sync_runs',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('account_id', sa.INTEGER(), nullable=False),
        sa.Column('status', sa.VARCHAR(length=20), nullable=False),
        sa.Column('content_count', sa.INTEGER(), nullable=False),
        sa.Column('metric_count', sa.INTEGER(), nullable=False),
        sa.Column('message', sa.VARCHAR(length=500), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('automation_run_id', sa.INTEGER(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['platform_accounts.id'], name='metrics_sync_runs_account_id_fkey'),
        sa.ForeignKeyConstraint(['automation_run_id'], ['automation_runs.id'], name='fk_sync_automation_run', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='metrics_sync_runs_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='metrics_sync_runs_pkey')
    )
    op.create_index('ix_metrics_sync_runs_account_id', 'metrics_sync_runs', ['account_id'], unique=False)
    op.create_index('ix_metrics_sync_runs_automation_run_id', 'metrics_sync_runs', ['automation_run_id'], unique=False)
    op.create_index('ix_metrics_sync_runs_user_id', 'metrics_sync_runs', ['user_id'], unique=False)
    op.create_table('publish_jobs',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), nullable=False),
        sa.Column('account_id', sa.INTEGER(), nullable=False),
        sa.Column('asset_id', sa.INTEGER(), nullable=False),
        sa.Column('platform', sa.VARCHAR(length=32), nullable=False),
        sa.Column('title', sa.VARCHAR(length=255), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=False),
        sa.Column('tags_json', sa.TEXT(), nullable=False),
        sa.Column('status', sa.VARCHAR(length=20), nullable=False),
        sa.Column('error_message', sa.VARCHAR(length=500), nullable=True),
        sa.Column('submitted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('confirmed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('plan_id', sa.INTEGER(), nullable=True),
        sa.Column('options_json', sa.TEXT(), server_default=sa.text("'{}'::text"), nullable=False),
        sa.Column('scheduled_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('image_asset_ids_json', sa.TEXT(), server_default=sa.text("'[]'::text"), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['platform_accounts.id'], name='publish_jobs_account_id_fkey'),
        sa.ForeignKeyConstraint(['asset_id'], ['media_assets.id'], name='publish_jobs_asset_id_fkey'),
        sa.ForeignKeyConstraint(['plan_id'], ['publish_plans.id'], name='publish_jobs_plan_id_fkey'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='publish_jobs_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='publish_jobs_pkey')
    )
    op.create_index('ix_publish_jobs_plan_id', 'publish_jobs', ['plan_id'], unique=False)
    op.create_index('ix_publish_jobs_user_id', 'publish_jobs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_publish_jobs_user_id', table_name='publish_jobs')
    op.drop_index('ix_publish_jobs_plan_id', table_name='publish_jobs')
    op.drop_table('publish_jobs')
    op.drop_index('ix_metrics_sync_runs_user_id', table_name='metrics_sync_runs')
    op.drop_index('ix_metrics_sync_runs_automation_run_id', table_name='metrics_sync_runs')
    op.drop_index('ix_metrics_sync_runs_account_id', table_name='metrics_sync_runs')
    op.drop_table('metrics_sync_runs')
    op.drop_index('ix_content_metrics_content_id', table_name='content_metrics')
    op.drop_table('content_metrics')
    op.drop_index('ix_published_contents_user_id', table_name='published_contents')
    op.drop_index('ix_published_contents_account_id', table_name='published_contents')
    op.drop_table('published_contents')
    op.drop_index('ix_publish_plans_user_id', table_name='publish_plans')
    op.drop_table('publish_plans')
    op.drop_index('ix_automation_runs_user_id', table_name='automation_runs')
    op.drop_index('ix_automation_runs_task_id', table_name='automation_runs')
    op.drop_table('automation_runs')
    op.drop_index('ix_platform_accounts_user_id', table_name='platform_accounts')
    op.drop_table('platform_accounts')
    op.drop_index('ix_media_assets_user_id', table_name='media_assets')
    op.drop_table('media_assets')
    op.drop_index('ix_automation_tasks_user_id', table_name='automation_tasks')
    op.drop_table('automation_tasks')
    op.drop_index('ix_analytics_reports_user_id', table_name='analytics_reports')
    op.drop_table('analytics_reports')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
