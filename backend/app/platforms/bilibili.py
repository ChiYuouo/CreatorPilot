"""B 站适配器：通过 vendored biliup 命令完成登录和上传。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from importlib import import_module
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from app.platforms.base import PlatformAdapter


def _runtime() -> Any:
    return import_module("uploader.bilibili_uploader.runtime")


def _account_file(account_name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", account_name):
        raise ValueError("账号标识格式不正确")
    return Path(import_module("conf").BASE_DIR) / "cookies" / f"bilibili_{account_name}.json"


class BilibiliAdapter(PlatformAdapter):
    async def collect_works(self, account_name: str, *, max_pages: int = 10) -> dict[str, Any]:
        from app.platforms.bilibili_metrics import collect_works
        return await collect_works(_account_file(account_name), max_pages=max_pages)

    async def login(self, account_name: str, *, headless: bool = False, qrcode_callback: Any = None) -> dict[str, Any]:
        if sys.platform != "win32":
            return {"success": False, "message": "B 站扫码登录目前需要在本机 Windows 终端运行"}
        binary = await asyncio.to_thread(_runtime().ensure_biliup_binary, False)
        path = _account_file(account_name)
        path.parent.mkdir(exist_ok=True)
        # biliup 在交互终端打印二维码，需要单独打开可见终端。
        process = await asyncio.create_subprocess_exec(
            str(binary), "-u", str(path), "login", creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        try:
            code = await process.wait()
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        valid = code == 0 and await self.check_login(account_name)
        return {"success": valid, "message": "扫码登录成功" if valid else "B 站扫码未完成，请重试", "account_file": str(path)}

    async def check_login(self, account_name: str) -> bool:
        path = _account_file(account_name)
        if not path.exists():
            return False
        result = await asyncio.to_thread(_runtime().run_biliup_command, ["-u", str(path), "renew"])
        return result.returncode == 0

    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        if not await self.check_login(content["account_name"]):
            return {"status": "login_expired", "platform": "bilibili", "platform_content_id": None}
        raw = content.get("scheduled_at")
        date: datetime | int = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else 0
        if isinstance(date, datetime) and date.tzinfo is None:
            raise ValueError("预约时间必须包含时区")
        args = [
            "-u", str(_account_file(content["account_name"])), "upload", content["video_path"],
            "--title", content["title"], "--desc", content.get("description", ""),
            "--tid", str(int(content.get("options", {}).get("tid", 0))),
        ]
        tags = content.get("tags", [])
        if tags:
            args.extend(["--tag", ",".join(tags)])
        if isinstance(date, datetime):
            args.extend(["--dtime", str(int(date.timestamp()))])
        result = await asyncio.to_thread(_runtime().run_biliup_command, args)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "").strip() or "B 站上传失败")
        return {"status": "submitted", "platform": "bilibili", "platform_content_id": None}

    async def fetch_metrics(self, content_id: str) -> dict[str, Any]:
        raise NotImplementedError("B 站指标回收尚未接入")
