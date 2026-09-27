"""已发布内容及每日累计指标。"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class PublishedContent(Base, TimestampMixin):
    __tablename__ = "published_contents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("platform_accounts.id"), index=True)
    platform_content_id: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint("account_id", "platform_content_id", name="uq_account_platform_content"),)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[list["ContentMetric"]] = relationship(
        back_populates="content", cascade="all, delete-orphan"
    )


class ContentMetric(Base, TimestampMixin):
    __tablename__ = "content_metrics"
    __table_args__ = (UniqueConstraint("content_id", "metric_date", name="uq_content_metric_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(
        ForeignKey("published_contents.id", ondelete="CASCADE"), index=True
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    views: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    favorites: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    follower_gain: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    platform_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content: Mapped[PublishedContent] = relationship(back_populates="metrics")


class MetricsSyncRun(Base, TimestampMixin):
    __tablename__ = "metrics_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("platform_accounts.id"), index=True)
    automation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_runs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    content_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metric_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(String(500))


class SavedAnalyticsReport(Base, TimestampMixin):
    __tablename__ = "analytics_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    # 历史报告保存原始内容 ID，不随作品删除而删除。
    content_id: Mapped[int | None] = mapped_column(Integer)
    report: Mapped[str] = mapped_column(Text)
    input_snapshot: Mapped[str] = mapped_column(Text)
    content_count: Mapped[int] = mapped_column(Integer)
    excluded_without_metrics: Mapped[int] = mapped_column(Integer, default=0)
    without_metrics_count: Mapped[int] = mapped_column(Integer, default=0)
    days: Mapped[int | None] = mapped_column(Integer)
