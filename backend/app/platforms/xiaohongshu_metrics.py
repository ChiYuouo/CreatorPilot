"""小红书笔记管理页只读采集；由页面发出签名请求并触发滚动分页。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.platforms.metrics_common import CollectionError, exact_count, platform_time

MANAGE_URL = "https://creator.xiaohongshu.com/new/note-manager"
LIST_PATH = "/api/galaxy/v2/creator/note/user/posted"
METRICS = {"views": "view_count", "likes": "likes", "comments": "comments_count",
           "favorites": "collected_count", "shares": "shared_count"}


def parse_page(payload: Any) -> tuple[list[Any], int]:
    if not isinstance(payload, dict) or payload.get("code") != 0 or payload.get("success") is not True:
        raise CollectionError("小红书拒绝作品请求，请检查登录态或完成平台验证")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
        raise CollectionError("小红书作品列表结构已变化，未写入本次数据")
    cursor = data.get("page")
    if type(cursor) is not int or cursor < -1:
        raise CollectionError("小红书作品分页信息缺失")
    if not data["notes"] and cursor != -1:
        raise CollectionError("小红书返回空页但仍有下一页，请重新同步")
    return data["notes"], cursor


def normalize_work(item: Any, collected_at: datetime) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not re.fullmatch(r"[0-9a-f]{24}", item["id"]):
        raise CollectionError("小红书作品标识无效")
    # 官方笔记管理页：Published=1，Public=0；禁止将审核、预约和私密笔记入库。
    if "tab_status" not in item or "permission_code" not in item:
        raise CollectionError("小红书作品公开状态缺失，未写入本次数据")
    if item["tab_status"] != 1 or item["permission_code"] != 0 or item.get("high_self") or item.get("schedule_post_time"):
        return None
    published_at = platform_time(item.get("time"), milliseconds=True)
    if published_at is None or published_at.year < 2013 or published_at > collected_at:
        return None
    return {"platform_content_id": item["id"], "title": str(item.get("display_title") or "无标题笔记")[:255],
            "published_at": published_at.isoformat(),
            "metrics": {**{name: exact_count(item.get(key)) for name, key in METRICS.items()}, "follower_gain": None},
            "platform_updated_at": None}


async def collect_works(cookie_file: Path, *, max_pages: int = 10) -> dict[str, Any]:
    if not cookie_file.is_file():
        return {"status": "login_expired", "message": "小红书登录文件不存在，请重新登录"}
    from patchright.async_api import async_playwright
    from patchright.async_api import TimeoutError as BrowserTimeout

    collected_at = datetime.now(timezone.utc)
    works: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    seen_cursors: set[int] = set()
    skipped = 0
    queue: asyncio.Queue[Any] = asyncio.Queue()
    max_pages = max(1, min(max_pages, 100))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chromium")
        try:
            context = await browser.new_context(storage_state=str(cookie_file))
            page = await context.new_page()
            def capture(response: Any) -> None:
                parsed = urlparse(response.url)
                if parsed.hostname == "creator.xiaohongshu.com" and parsed.path == LIST_PATH and parse_qs(parsed.query).get("tab") == ["0"]:
                    queue.put_nowait(response)
            page.on("response", capture)
            try:
                await page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=35000)
                requested_page = 0
                for number in range(max_pages):
                    try:
                        response = await asyncio.wait_for(queue.get(), timeout=20)
                    except TimeoutError as exc:
                        if "login" in page.url:
                            return {"status": "login_expired", "message": "小红书登录态已过期"}
                        raise CollectionError("未收到小红书作品分页响应，请检查登录态或后台页面变化") from exc
                    if response.status != 200:
                        raise CollectionError("小红书作品请求失败，请完成平台验证后重试")
                    query = parse_qs(urlparse(response.url).query)
                    if query.get("page") != [str(requested_page)]:
                        raise CollectionError("小红书分页顺序异常，未写入本次数据")
                    items, cursor = parse_page(await response.json())
                    for item in items:
                        work = normalize_work(item, collected_at)
                        work_id = item["id"]
                        if work_id in seen_ids:
                            raise CollectionError("小红书作品分页重复，请重新同步")
                        seen_ids.add(work_id)
                        if work is None:
                            skipped += 1
                        else:
                            works[work_id] = work
                    more = cursor != -1
                    if not more:
                        break
                    if cursor <= requested_page or cursor in seen_cursors:
                        raise CollectionError("小红书作品分页游标异常")
                    seen_cursors.add(cursor)
                    requested_page = cursor
                    if number + 1 >= max_pages:
                        break
                    # 列表使用 IntersectionObserver；滚动哨兵让网站自行签名下一页。
                    if queue.empty():
                        await page.locator("#notes-request").scroll_into_view_if_needed(timeout=10000)
            except BrowserTimeout as exc:
                if "login" in page.url:
                    return {"status": "login_expired", "message": "小红书登录态已过期"}
                raise CollectionError("小红书作品页面加载或分页超时") from exc
            finally:
                page.remove_listener("response", capture)
        finally:
            await browser.close()
    return {"status": "completed", "works": list(works.values()), "collected_at": collected_at.isoformat(),
            "truncated": more, "skipped": skipped,
            "message": "小红书笔记管理累计指标；未提供的单篇新增粉丝和平台更新时间保留为空"}
