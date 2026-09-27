"""Celery 应用与周期扫描入口。仅由 worker/beat 进程启动。"""

from celery import Celery

from app.core.config import settings

celery_app = Celery("creatorpilot", broker=settings.celery_broker_url or settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    imports=("app.tasks.automation", "app.tasks.publishing", "app.tasks.metrics"),
    task_routes={"app.tasks.publishing.publish_job": {"queue": "publishing"},
                 "app.tasks.metrics.sync_account": {"queue": "publishing"}},
    beat_schedule={
        "dispatch-due-tasks": {
            "task": "app.tasks.automation.dispatch_due_tasks",
            "schedule": 60.0,
        },
        # 兜住"Worker 被关掉/崩掉、用户又没点取消"的残留发布任务
        "reap-stale-publish-jobs": {
            "task": "app.tasks.publishing.reap_stale_jobs",
            "schedule": 300.0,
        },
    },
)
