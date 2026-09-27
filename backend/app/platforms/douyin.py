"""抖音平台适配器：把 CreatorPilot 请求交给 vendored social-auto-upload。"""

from __future__ import annotations

from datetime import datetime
from importlib import import_module
from pathlib import Path
import re
from typing import Any

from app.platforms.base import PlatformAdapter
from app.platforms.douyin_note import DouyinNoteFormError, note_uploader_class


def _uploader() -> Any:
    """运行时才加载上游包，避免未启用平台发布时影响现有功能。"""
    try:
        return import_module("uploader.douyin_uploader.main")
    except ImportError as exc:
        raise RuntimeError(
            "平台上传依赖未安装，请安装 backend/vendor/social_auto_upload 并准备 Patchright 浏览器"
        ) from exc


def _account_file(account_name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", account_name):
        raise ValueError("账号标识只能包含字母、数字、下划线和连字符")
    runtime_home = Path(import_module("conf").BASE_DIR)
    return runtime_home / "cookies" / f"douyin_{account_name}.json"


def _publish_date(content: dict[str, Any]) -> datetime | int:
    raw = content.get("scheduled_at")
    if not raw:
        return 0
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("预约时间必须包含时区")
    return value.astimezone().replace(tzinfo=None)


class DouyinAdapter(PlatformAdapter):
    async def collect_works(self, account_name: str, *, max_pages: int = 10) -> dict[str, Any]:
        from app.platforms.douyin_metrics import collect_works
        return await collect_works(_account_file(account_name), max_pages=max_pages)

    async def login(self, account_name: str, *, headless: bool = False, qrcode_callback: Any = None) -> dict[str, Any]:
        return await _uploader().douyin_setup(
            str(_account_file(account_name)), handle=True, return_detail=True,
            headless=headless, qrcode_callback=qrcode_callback,
        )

    async def check_login(self, account_name: str) -> bool:
        return await _uploader().cookie_auth(str(_account_file(account_name)))

    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """直接调用上游上传函数；返回 submitted，不推断平台作品 ID。"""
        sau = _uploader()
        scheduled_at = _publish_date(content)
        account_file = _account_file(content["account_name"])
        if not await sau.douyin_setup(str(account_file), handle=False):
            # 适配器跑在独立子进程里，异常穿不过子进程边界，只能用返回值报告状态
            return {"status": "login_expired", "platform": "douyin", "platform_content_id": None}
        if content.get("media_type") == "image":
            note = note_uploader_class(sau.DouYinNote)(
                image_paths=content["image_paths"], note=content.get("description", ""),
                title=content["title"], tags=content.get("tags", []),
                publish_date=scheduled_at or 0, account_file=str(account_file),
                publish_strategy=(sau.DOUYIN_PUBLISH_STRATEGY_SCHEDULED
                                  if scheduled_at else sau.DOUYIN_PUBLISH_STRATEGY_IMMEDIATE),
                headless=content.get("headless", True), debug=False,
            )
            try:
                await note.douyin_upload_note()
            except DouyinNoteFormError as exc:
                return {"status": "failed", "platform": "douyin", "submission_attempted": False, "message": str(exc)}
            return {"status": "submitted", "platform": "douyin", "platform_content_id": None}
        uploader = sau.DouYinVideo(
            content["title"],
            str(Path(content["video_path"])),
            content.get("tags", []),
            scheduled_at or 0,
            str(account_file),
            desc=content.get("description", ""),
            publish_strategy=(
                sau.DOUYIN_PUBLISH_STRATEGY_SCHEDULED
                if scheduled_at else sau.DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
            ),
            headless=content.get("headless", True),
            debug=False,
        )
        await uploader.douyin_upload_video()
        return {"status": "submitted", "platform": "douyin", "platform_content_id": None}

    async def fetch_metrics(self, content_id: str) -> dict[str, Any]:
        raise NotImplementedError("抖音指标回收尚未接入")
