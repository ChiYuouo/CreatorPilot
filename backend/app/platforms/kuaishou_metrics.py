"""监听快手后台实际作品请求，复用请求参数进行只读分页。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from app.platforms.metrics_common import CollectionError

MANAGE_URL = "https://cp.kuaishou.com/article/manage/video"
LIST_PATH = "/rest/cp/works/v2/video/pc/photo/list"


def parse_page(payload: Any) -> tuple[list[Any], str, int]:
    if not isinstance(payload, dict) or payload.get("result") != 1:
        raise CollectionError("快手拒绝作品请求，请检查登录态或完成平台验证")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise CollectionError("快手作品接口结构已变化")
    total, cursor = data.get("total"), data.get("nextCursor")
    if type(total) is not int or total < 0 or not isinstance(cursor, (str, int)):
        raise CollectionError("快手作品分页信息缺失")
    return data["list"], str(cursor), total


def normalize_work(item: Any, collected_at: datetime) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        raise CollectionError("快手稿件结构已变化")
    # 已发布、公开且审核通过；不收录草稿、预约或非本人作品。
    if item.get("publishStatus") != 4 or item.get("photoStatus") != 0 or item.get("judgementStatus") != 1 or item.get("photoOwner") is not True:
        return None
    work_id = item.get("workId")
    if not isinstance(work_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", work_id):
        raise CollectionError("快手作品标识缺失")
    try:
        published_at = datetime.fromtimestamp(float(item["uploadTime"]) / 1000, timezone.utc)
    except (KeyError, ValueError, TypeError, OSError, OverflowError):
        return None
    if published_at.year < 2011 or published_at > collected_at:
        return None
    metrics: dict[str, int | None] = {"favorites": None, "shares": None, "follower_gain": None}
    for name, key in (("views", "playCount"), ("likes", "likeCount"), ("comments", "commentCount")):
        value = item.get(key)
        metrics[name] = value if type(value) is int and 0 <= value <= 2_147_483_647 else None
    return {"platform_content_id": work_id, "title": str(item.get("title") or "无标题作品")[:255],
            "published_at": published_at.isoformat(), "metrics": metrics, "platform_updated_at": None}


async def collect_works(cookie_file: Path, *, max_pages: int = 10) -> dict[str, Any]:
    if not cookie_file.is_file():
        return {"status": "login_expired", "message": "登录文件不存在，请重新登录"}
    from patchright.async_api import async_playwright
    from patchright.async_api import TimeoutError as BrowserTimeout

    collected_at = datetime.now(timezone.utc)
    works: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    seen_cursors: set[str] = set()
    skipped = 0
    max_pages = max(1, min(max_pages, 100))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chromium")
        try:
            context = await browser.new_context(storage_state=str(cookie_file))
            page = await context.new_page()
            def matches(response: Any) -> bool:
                parsed = urlparse(response.url)
                return parsed.hostname == "cp.kuaishou.com" and parsed.path == LIST_PATH
            try:
                async with page.expect_response(matches, timeout=45000) as captured:
                    await page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=35000)
                response = await captured.value
            except BrowserTimeout as exc:
                if "passport" in page.url or "login" in page.url:
                    return {"status": "login_expired", "message": "快手登录态已过期"}
                raise CollectionError("未捕获快手作品请求，请检查登录态或平台验证") from exc
            if response.status != 200:
                raise CollectionError("快手作品请求失败，请稍后重试或完成平台验证")
            body = response.request.post_data_json
            if not isinstance(body, dict) or "cursor" not in body:
                raise CollectionError("快手分页请求结构已变化")
            payload = await response.json()
            expected_total: int | None = None
            for number in range(max_pages):
                items, cursor, total = parse_page(payload)
                if expected_total is not None and expected_total != total:
                    raise CollectionError("快手作品列表在分页时发生变化，请重新同步")
                expected_total = total
                for item in items:
                    if not isinstance(item, dict) or not item.get("workId"):
                        raise CollectionError("快手作品结构已变化")
                    work_id = str(item["workId"])
                    if work_id in seen_ids:
                        raise CollectionError("快手作品分页重复，请重新同步")
                    seen_ids.add(work_id)
                    work = normalize_work(item, collected_at)
                    if work is None:
                        skipped += 1
                    else:
                        works[work_id] = work
                more = len(seen_ids) < total
                if len(seen_ids) > total:
                    raise CollectionError("快手作品总数与列表不一致，请重新同步")
                if not more:
                    break
                if not items or cursor in ("", "0", "-1") or cursor in seen_cursors:
                    raise CollectionError("快手作品分页游标异常，未写入数据")
                seen_cursors.add(cursor)
                if number + 1 >= max_pages:
                    break
                body = {**body, "cursor": cursor}
                next_response = await context.request.post(response.url, data=body,
                    headers={"Referer": MANAGE_URL}, timeout=30000)
                if not next_response.ok:
                    raise CollectionError("快手作品分页请求失败")
                payload = await next_response.json()
        finally:
            await browser.close()
    return {"status": "completed", "works": list(works.values()), "collected_at": collected_at.isoformat(),
            "truncated": more, "skipped": skipped,
            "message": "快手提供播放、点赞、评论；发布时间使用平台记录的上传时间"}
