"""视频号助手作品管理只读采集，复用后台发出的请求及分页参数。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.platforms.metrics_common import CollectionError, exact_count, platform_time

MANAGE_URL = "https://channels.weixin.qq.com/platform/post/list"
LIST_PATH = "/cgi-bin/mmfinderassistant-bin/post/post_list"
METRICS = {"views": "playCount", "likes": "likeCount", "comments": "commentCount"}


def parse_page(payload: Any) -> tuple[list[Any], int]:
    if not isinstance(payload, dict) or payload.get("errCode") != 0:
        raise CollectionError("视频号拒绝作品请求，请重新登录或完成平台验证")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise CollectionError("视频号作品列表结构已变化，未写入本次数据")
    total = data.get("totalCount")
    if type(total) is not int or total < 0 or total > 0 and not data["list"]:
        raise CollectionError("视频号作品分页信息无效")
    return data["list"], total


def normalize_work(item: Any, collected_at: datetime) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        raise CollectionError("视频号作品结构已变化")
    work_id = str(item.get("objectId") or "")
    if not work_id.isascii() or not work_id.isdigit() or len(work_id) > 100:
        raise CollectionError("视频号作品标识无效")
    if "visibleType" not in item:
        raise CollectionError("视频号作品可见状态缺失，未写入本次数据")
    if item["visibleType"] != 1 or item.get("isPostDelay") or item.get("isInReview"):
        return None
    if "status" in item and item["status"] != 1:
        return None
    # 未获得明确审核/发布状态时拒绝采集，不能只根据可见范围猜测已公开。
    if "status" not in item:
        raise CollectionError("视频号作品发布状态缺失，需核对当前后台字段")
    raw_time = item.get("effectiveTime") or item.get("createTime")
    published_at = platform_time(raw_time)
    if published_at is None or published_at.year < 2020 or published_at > collected_at:
        return None
    desc = item.get("desc")
    if not isinstance(desc, dict):
        raise CollectionError("视频号作品描述结构已变化")
    return {"platform_content_id": work_id, "title": str(desc.get("description") or "无标题作品")[:255],
            "published_at": published_at.isoformat(),
            "metrics": {**{name: exact_count(item.get(key)) for name, key in METRICS.items()},
                        "favorites": None, "shares": None, "follower_gain": None},
            "platform_updated_at": None}


async def collect_works(cookie_file: Path, *, max_pages: int = 10) -> dict[str, Any]:
    if not cookie_file.is_file():
        return {"status": "login_expired", "message": "视频号登录文件不存在，请到账号管理扫码绑定"}
    from patchright.async_api import async_playwright
    from patchright.async_api import TimeoutError as BrowserTimeout

    collected_at = datetime.now(timezone.utc)
    works: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    skipped = 0
    max_pages = max(1, min(max_pages, 100))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chromium")
        try:
            context = await browser.new_context(storage_state=str(cookie_file))
            page = await context.new_page()
            def matches(response: Any) -> bool:
                parsed = urlparse(response.url)
                return parsed.hostname == "channels.weixin.qq.com" and parsed.path == LIST_PATH
            try:
                async with page.expect_response(matches, timeout=45000) as captured:
                    await page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=35000)
                response = await captured.value
            except BrowserTimeout as exc:
                if "login" in page.url:
                    return {"status": "login_expired", "message": "视频号登录态已过期，请重新登录"}
                raise CollectionError("未收到视频号作品列表，请检查登录态或完成平台验证") from exc
            if response.status != 200:
                raise CollectionError("视频号作品请求失败，请完成平台验证后重试")
            body = response.request.post_data_json
            if not isinstance(body, dict) or body.get("currentPage") != 1 or type(body.get("pageSize")) is not int or body["pageSize"] <= 0:
                raise CollectionError("视频号作品请求分页结构已变化")
            # 透传当前浏览器的鉴权请求头，不落盘、不回传给业务层。
            headers = {key: value for key, value in (await response.request.all_headers()).items()
                       if key.lower() not in ("host", "content-length", "cookie") and not key.startswith(":")}
            payload = await response.json()
            expected_total: int | None = None
            for number in range(1, max_pages + 1):
                items, total = parse_page(payload)
                if expected_total is not None and total != expected_total:
                    raise CollectionError("视频号作品列表在分页时发生变化，请重新同步")
                expected_total = total
                for item in items:
                    work = normalize_work(item, collected_at)
                    work_id = str(item["objectId"])
                    if work_id in seen_ids:
                        raise CollectionError("视频号作品分页重复，请重新同步")
                    seen_ids.add(work_id)
                    if work is None:
                        skipped += 1
                    else:
                        works[work_id] = work
                if len(seen_ids) > total:
                    raise CollectionError("视频号作品总数与列表不一致")
                more = len(seen_ids) < total
                if not more or number >= max_pages:
                    break
                next_response = await context.request.post(response.url,
                    data={**body, "currentPage": number + 1}, headers=headers, timeout=30000)
                if not next_response.ok:
                    raise CollectionError("视频号作品分页请求失败")
                payload = await next_response.json()
        finally:
            await browser.close()
    return {"status": "completed", "works": list(works.values()), "collected_at": collected_at.isoformat(),
            "truncated": more, "skipped": skipped,
            "message": "视频号公开作品累计指标；后台未提供的指标保留为空"}
