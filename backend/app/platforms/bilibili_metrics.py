"""使用 biliup 登录文件只读获取 B 站创作中心公开稿件和累计指标。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.platforms.metrics_common import CollectionError

LIST_URL = "https://member.bilibili.com/x/web/archives"
METRICS = {"views": "view", "likes": "like", "comments": "reply",
           "favorites": "favorite", "shares": "share"}


def parse_page(payload: Any) -> tuple[list[Any], int, int]:
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise CollectionError("B 站拒绝作品请求，请检查登录态或平台验证")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("page"), dict):
        raise CollectionError("B 站作品接口结构已变化")
    count, size = data["page"].get("count"), data["page"].get("ps")
    if type(count) is not int or count < 0 or type(size) is not int or size <= 0:
        raise CollectionError("B 站作品分页信息无效")
    items = data.get("arc_audits", [] if count == 0 else None)
    if not isinstance(items, list) or (count > 0 and not items):
        raise CollectionError("B 站作品列表缺失，未写入本次数据")
    return items, count, size


def normalize_work(item: Any, collected_at: datetime) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not isinstance(item.get("Archive"), dict):
        raise CollectionError("B 站稿件结构已变化")
    archive = item["Archive"]
    # 审核中、预约、私密、仅自己可见的稿件不能作为已公开作品。
    if archive.get("state") != 0 or archive.get("no_public") or archive.get("is_only_self"):
        return None
    aid = archive.get("aid")
    if type(aid) is not int or aid <= 0:
        raise CollectionError("B 站稿件标识缺失")
    try:
        published_at = datetime.fromtimestamp(float(archive["ptime"]), timezone.utc)
    except (KeyError, ValueError, TypeError, OSError, OverflowError):
        return None
    if published_at.year < 2009 or published_at > collected_at:
        return None
    stats = item.get("stat") or {}
    if not isinstance(stats, dict):
        raise CollectionError("B 站稿件指标结构已变化")
    metrics: dict[str, int | None] = {"follower_gain": None}
    for name, key in METRICS.items():
        value = stats.get(key)
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        metrics[name] = value if type(value) is int and 0 <= value <= 2_147_483_647 else None
    return {"platform_content_id": str(aid), "title": str(archive.get("title") or "无标题作品")[:255],
            "published_at": published_at.isoformat(), "metrics": metrics, "platform_updated_at": None}


def _collect(cookie_file: Path, max_pages: int) -> dict[str, Any]:
    import requests

    if not cookie_file.is_file():
        return {"status": "login_expired", "message": "登录文件不存在，请重新绑定账号"}
    try:
        login = json.loads(cookie_file.read_text(encoding="utf-8"))
        cookies = login["cookie_info"]["cookies"]
        if not isinstance(cookies, list) or not any(c.get("name") == "SESSDATA" and c.get("value") for c in cookies):
            raise ValueError("missing cookies")
    except (KeyError, ValueError, TypeError, AttributeError):
        return {"status": "login_expired", "message": "B 站登录文件不可用，请重新登录"}
    collected_at = datetime.now(timezone.utc)
    works: dict[str, dict[str, Any]] = {}
    seen_ids: set[int] = set()
    skipped = 0
    max_pages = max(1, min(max_pages, 100))
    expected: tuple[int, int] | None = None
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://member.bilibili.com/"})
        for cookie in cookies:
            session.cookies.set(cookie["name"], cookie["value"], domain=".bilibili.com")
        for number in range(1, max_pages + 1):
            response = session.get(LIST_URL, params={"status": "pubed", "pn": number, "ps": 20}, timeout=30)
            if response.status_code == 401:
                return {"status": "login_expired", "message": "B 站登录态已过期"}
            if response.status_code != 200:
                raise CollectionError("B 站作品请求失败，请稍后重试或完成平台验证")
            try:
                payload = response.json()
            except ValueError as exc:
                raise CollectionError("B 站返回了无法识别的数据") from exc
            if isinstance(payload, dict) and payload.get("code") == -101:
                return {"status": "login_expired", "message": "B 站登录态已过期"}
            items, count, size = parse_page(payload)
            if expected is not None and expected != (count, size):
                raise CollectionError("B 站作品列表在分页时发生变化，请重新同步")
            expected = count, size
            if len(items) > size:
                raise CollectionError("B 站作品分页大小异常")
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("Archive"), dict):
                    raise CollectionError("B 站稿件结构已变化")
                aid = item["Archive"].get("aid")
                if type(aid) is not int or aid <= 0 or aid in seen_ids:
                    raise CollectionError("B 站分页稿件标识无效或重复")
                seen_ids.add(aid)
                work = normalize_work(item, collected_at)
                if work is None:
                    skipped += 1
                elif work["platform_content_id"] in works:
                    raise CollectionError("B 站分页返回了重复稿件，请重新同步")
                else:
                    works[work["platform_content_id"]] = work
            more = number * size < count
            if not more:
                if len(seen_ids) != count:
                    raise CollectionError("B 站作品分页不完整，请重新同步")
                break
    return {"status": "completed", "works": list(works.values()), "collected_at": collected_at.isoformat(),
            "truncated": more, "skipped": skipped,
            "message": "已读取 B 站公开稿件；单篇新增粉丝及平台更新时间未提供"}


async def collect_works(cookie_file: Path, *, max_pages: int = 10) -> dict[str, Any]:
    return await asyncio.to_thread(_collect, cookie_file, max_pages)
