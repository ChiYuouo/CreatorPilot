"""抖音创作者后台只读采集。不修改上传器，不伪造缺失指标。

参考 SYNAPSEAUTOMATION 的 Cookie + creator aweme/list 路径，独立实现。
当前后台使用 /janus/douyin/creator/pc/work_list，监听页面请求后
复用浏览器参数分页；旧 aweme/list 仅兜底。接口变化明确失败。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.parse import parse_qsl, urlencode, urlunparse
from app.platforms.metrics_common import CollectionError

MANAGE_URL = "https://creator.douyin.com/creator-micro/content/manage"
LIST_URL = "https://creator.douyin.com/web/api/media/aweme/list"
WORK_LIST_PATH = "/janus/douyin/creator/pc/work_list"
METRIC_KEYS = {
    "views": ("view_count", "play_count", "play_count_v2"),
    "likes": ("like_count", "digg_count"),
    "comments": ("comment_count",),
    "favorites": ("favorite_count", "collect_count"),
    "shares": ("share_count",),
    "follower_gain": ("subscribe_count",),
}


def parse_page(payload: Any) -> tuple[list[dict[str, Any]], bool, Any]:
    if not isinstance(payload, dict):
        raise CollectionError("平台返回了无法识别的数据")
    for key in ("status_code", "code"):
        if key in payload and payload[key] not in (0, 200, "0", "200"):
            raise CollectionError("平台拒绝数据请求，请检查登录态或到平台完成验证")
    data = payload.get("data", payload)
    if not isinstance(data, dict) or not isinstance(data.get("aweme_list"), list):
        raise CollectionError("平台作品接口结构已变化，未写入数据")
    more = data.get("has_more") in (True, 1, "1")
    if "has_more" not in data:
        raise CollectionError("平台作品分页信息缺失，未写入数据")
    creator_items = data.get("items") or []
    if not isinstance(creator_items, list):
        raise CollectionError("平台指标结构已变化，未写入数据")
    items_by_id = {str(item.get("id")): item for item in creator_items if isinstance(item, dict)}
    works = []
    for aweme in data["aweme_list"]:
        if not isinstance(aweme, dict):
            works.append(aweme)
            continue
        item = items_by_id.get(str(aweme.get("aweme_id")), {})
        works.append({**aweme, "creator_metrics": item.get("metrics", {}),
                      "metrics_offline_update_time": item.get("metrics_offline_update_time")})
    return works, more, data.get("cursor", data.get("max_cursor"))


def normalize_work(item: Any, collected_at: datetime) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    work_id = str(item.get("aweme_id") or "")
    # 只接受平台稳定 ID、有效发布时间和已公开作品，不按标题推断身份。
    if not work_id.isdigit() or len(work_id) > 100:
        return None
    status = item.get("status") or {}
    if not isinstance(status, dict):
        return None
    if any(status.get(key) for key in ("is_delete", "is_prohibited", "is_private", "self_see", "in_reviewing")) or status.get("private_status", 0) not in (0, "0"):
        return None
    try:
        published_at = datetime.fromtimestamp(float(item["create_time"]), timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    if published_at > collected_at or published_at.year < 2016:
        return None
    stats = item.get("statistics") or {}
    if not isinstance(stats, dict):
        stats = {}
    creator_metrics = item.get("creator_metrics") or {}
    if isinstance(creator_metrics, dict):
        stats = {**stats, **creator_metrics}
    metrics: dict[str, int | None] = {"follower_gain": None}
    for name, aliases in METRIC_KEYS.items():
        value = next((stats[key] for key in aliases if stats.get(key) is not None), None)
        # 不解析“1.2万”等展示文本；0 与 null 分开，拒绝负数和非整数。
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        metrics[name] = value if type(value) is int and 0 <= value <= 2_147_483_647 else None
    return {
        "platform_content_id": work_id,
        "title": str(item.get("desc") or item.get("title") or "无标题作品")[:255],
        "published_at": published_at.isoformat(),
        "metrics": metrics,
        "platform_updated_at": _platform_update_time(item.get("metrics_offline_update_time"), collected_at),
    }


def _platform_update_time(value: Any, collected_at: datetime) -> str | None:
    try:
        timestamp = datetime.fromtimestamp(float(value), timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return timestamp.isoformat() if 2016 <= timestamp.year and timestamp <= collected_at else None


async def collect_works(cookie_file: Path, *, max_pages: int = 10) -> dict[str, Any]:
    if not cookie_file.is_file():
        return {"status": "login_expired", "message": "登录文件不存在，请重新绑定账号"}
    # Patchright 已随独立上传环境安装，主后端无需增加浏览器依赖。
    from patchright.async_api import async_playwright

    collected_at = datetime.now(timezone.utc)
    works: dict[str, dict[str, Any]] = {}
    skipped = 0
    truncated = False
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chromium")
        try:
            context = await browser.new_context(storage_state=str(cookie_file))
            page = await context.new_page()
            captured: asyncio.Queue[Any] = asyncio.Queue()
            listeners: set[asyncio.Task] = set()

            async def capture(response: Any) -> None:
                parsed = urlparse(response.url)
                if parsed.hostname != "creator.douyin.com" or parsed.path.rstrip("/") not in ("/web/api/media/aweme/list", WORK_LIST_PATH):
                    return
                try:
                    captured.put_nowait((await response.json(), response.url))
                except Exception:
                    pass

            def on_response(response: Any) -> None:
                task = asyncio.create_task(capture(response))
                listeners.add(task)
                task.add_done_callback(listeners.discard)

            page.on("response", on_response)
            try:
                await page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=45000)
                if "login" in page.url or "passport" in page.url:
                    return {"status": "login_expired", "message": "登录态已过期，请在账号管理重新登录"}
                try:
                    payload, request_url = await asyncio.wait_for(captured.get(), timeout=20)
                    parse_page(payload)
                except (TimeoutError, CollectionError):
                    response = await context.request.get(
                        LIST_URL, params={"cursor": 0, "count": 20, "status": 1},
                        headers={"Referer": MANAGE_URL}, timeout=30000,
                    )
                    if response.status in (401, 403):
                        return {"status": "login_expired", "message": "平台拒绝访问，请重新登录或完成验证"}
                    payload = await response.json()
                    request_url = LIST_URL

                seen_cursors: set[str] = set()
                for page_number in range(max(1, min(max_pages, 100))):
                    items, more, cursor = parse_page(payload)
                    for item in items:
                        work = normalize_work(item, collected_at)
                        if work is None:
                            skipped += 1
                        else:
                            works[work["platform_content_id"]] = work
                    if not more:
                        break
                    if cursor is None or str(cursor) in seen_cursors:
                        raise CollectionError("平台分页游标异常，未写入本次数据")
                    seen_cursors.add(str(cursor))
                    if page_number + 1 >= max_pages:
                        truncated = True
                        break
                    parsed = urlparse(request_url)
                    params = dict(parse_qsl(parsed.query))
                    cursor_key = "max_cursor" if parsed.path.rstrip("/") == WORK_LIST_PATH else "cursor"
                    params.update({cursor_key: str(cursor), "count": "20"})
                    next_url = urlunparse(parsed._replace(query=urlencode(params)))
                    response = await context.request.get(
                        next_url,
                        headers={"Referer": MANAGE_URL}, timeout=30000,
                    )
                    if not response.ok:
                        raise CollectionError("作品分页请求失败，未写入本次数据")
                    payload = await response.json()
            finally:
                page.remove_listener("response", on_response)
                if listeners:
                    await asyncio.gather(*listeners, return_exceptions=True)
        finally:
            await browser.close()
    return {
        "status": "completed", "works": list(works.values()),
        "collected_at": collected_at.isoformat(), "truncated": truncated, "skipped": skipped,
        "message": "已读取作品后台；接口未提供的指标保留为空",
    }
