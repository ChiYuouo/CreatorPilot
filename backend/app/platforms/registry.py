"""平台适配器注册入口；按平台标识创建实例，不预建未实现的平台。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.platforms.base import PlatformAdapter
from app.platforms.bilibili import BilibiliAdapter
from app.platforms.douyin import DouyinAdapter
from app.platforms.kuaishou import KuaishouAdapter
from app.platforms.tencent import TencentAdapter
from app.platforms.xiaohongshu import XiaohongshuAdapter


@dataclass(frozen=True)
class PlatformRegistration:
    key: str
    name: str
    title_max_length: int
    description_required: bool
    tags_max_count: int
    adapter_factory: Callable[[], PlatformAdapter]
    category_required: bool = False
    metrics_sync_supported: bool = False
    image_publish_supported: bool = False
    image_max_count: int = 0
    image_title_max_length: int = 20
    image_description_max_length: int = 1000


_PLATFORMS: dict[str, PlatformRegistration] = {
    "douyin": PlatformRegistration(
        key="douyin", name="抖音", title_max_length=30,
        description_required=False, tags_max_count=20,
        adapter_factory=DouyinAdapter,
        metrics_sync_supported=True, image_publish_supported=True, image_max_count=9,
    ),
    "kuaishou": PlatformRegistration(
        key="kuaishou", name="快手", title_max_length=30,
        description_required=False, tags_max_count=3, adapter_factory=KuaishouAdapter,
        metrics_sync_supported=True, image_publish_supported=True, image_max_count=9,
    ),
    "xiaohongshu": PlatformRegistration(
        key="xiaohongshu", name="小红书", title_max_length=20,
        description_required=False, tags_max_count=10, adapter_factory=XiaohongshuAdapter,
        metrics_sync_supported=True, image_publish_supported=True, image_max_count=9,
    ),
    "tencent": PlatformRegistration(
        key="tencent", name="视频号", title_max_length=30,
        description_required=False, tags_max_count=20, adapter_factory=TencentAdapter,
        metrics_sync_supported=True,
    ),
    "bilibili": PlatformRegistration(
        key="bilibili", name="B 站", title_max_length=80,
        description_required=True, tags_max_count=20, adapter_factory=BilibiliAdapter,
        category_required=True,
        metrics_sync_supported=True,
    ),
}


def list_platforms() -> tuple[PlatformRegistration, ...]:
    """只向业务层和前端暴露已接通的平台注册信息。"""
    return tuple(_PLATFORMS.values())


def get_platform(platform: str) -> PlatformRegistration:
    try:
        return _PLATFORMS[platform]
    except KeyError as exc:
        raise ValueError(f"尚不支持平台：{platform}") from exc


def get_adapter(platform: str) -> PlatformAdapter:
    return get_platform(platform).adapter_factory()
