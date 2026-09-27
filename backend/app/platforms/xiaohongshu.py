"""小红书视频适配器：直接调用 vendored 上传器。"""

from __future__ import annotations

from datetime import datetime
from importlib import import_module
from pathlib import Path
import re
from typing import Any

from app.platforms.base import PlatformAdapter


def _uploader() -> Any:
    try:
        return import_module("uploader.xiaohongshu_uploader.main")
    except ImportError as exc:
        raise RuntimeError("小红书上传依赖未安装，请检查 Publisher 环境") from exc


def _account_file(account_name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", account_name):
        raise ValueError("账号标识格式不正确")
    return Path(import_module("conf").BASE_DIR) / "cookies" / f"xiaohongshu_{account_name}.json"


def _publish_date(content: dict[str, Any]) -> datetime | int:
    raw = content.get("scheduled_at")
    if not raw:
        return 0
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("预约时间必须包含时区")
    return value.astimezone().replace(tzinfo=None)


class XiaohongshuAdapter(PlatformAdapter):
    async def collect_works(self, account_name: str, *, max_pages: int = 10) -> dict[str, Any]:
        from app.platforms.xiaohongshu_metrics import collect_works
        return await collect_works(_account_file(account_name), max_pages=max_pages)

    async def login(self, account_name: str, *, headless: bool = False, qrcode_callback: Any = None) -> dict[str, Any]:
        return await _uploader().xiaohongshu_setup(
            str(_account_file(account_name)), handle=True, return_detail=True,
            headless=headless, qrcode_callback=qrcode_callback,
        )

    async def check_login(self, account_name: str) -> bool:
        return await _uploader().cookie_auth(str(_account_file(account_name)))

    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        sau = _uploader()
        path = _account_file(content["account_name"])
        if not await sau.xiaohongshu_setup(str(path), handle=False):
            return {"status": "login_expired", "platform": "xiaohongshu", "platform_content_id": None}
        date = _publish_date(content)
        if content.get("media_type") == "image":
            note = sau.XiaoHongShuNote(
                image_paths=content["image_paths"], note=content.get("description", ""),
                title=content["title"], tags=content.get("tags", []),
                publish_date=date or 0, account_file=str(path),
                publish_strategy=(sau.XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED
                                  if date else sau.XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE),
                headless=content.get("headless", True), debug=False,
            )
            await note.xiaohongshu_upload_note()
            return {"status": "submitted", "platform": "xiaohongshu", "platform_content_id": None}
        video = sau.XiaoHongShuVideo(
            title=content["title"],
            file_path=str(Path(content["video_path"])),
            tags=content.get("tags", []),
            publish_date=date,
            account_file=str(path),
            desc=content.get("description", ""),
            publish_strategy=(
                sau.XIAOHONGSHU_PUBLISH_STRATEGY_SCHEDULED
                if date else sau.XIAOHONGSHU_PUBLISH_STRATEGY_IMMEDIATE
            ),
            headless=content.get("headless", True),
            debug=False,
        )
        await video.xiaohongshu_upload_video()
        return {"status": "submitted", "platform": "xiaohongshu", "platform_content_id": None}

    async def fetch_metrics(self, content_id: str) -> dict[str, Any]:
        raise NotImplementedError("小红书指标回收尚未接入")
