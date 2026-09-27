"""ORM 模型。Alembic 通过 app.db.base 导入所有模型以生成迁移。"""

from app.db.base import Base  # noqa: F401
from app.models.analytics import ContentMetric, PublishedContent, MetricsSyncRun, SavedAnalyticsReport  # noqa: F401
from app.models.automation import AutomationRun, AutomationTask  # noqa: F401
from app.models.publishing import MediaAsset, PlatformAccount, PublishJob, PublishPlan  # noqa: F401
from app.models.user import User  # noqa: F401
