"""只读采集共用的异常、精确数值和时间转换。"""

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


class CollectionError(RuntimeError):
    pass


def exact_count(value: Any) -> int | None:
    if isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    return value if type(value) is int and 0 <= value <= 2_147_483_647 else None


def platform_time(value: Any, *, milliseconds: bool = False) -> datetime | None:
    try:
        if type(value) in (int, float) or isinstance(value, str) and value.isascii() and value.isdigit():
            return datetime.fromtimestamp(float(value) / (1000 if milliseconds else 1), timezone.utc)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # 后台无时区的日期文本采用北京时间，不能使用机器本地时区。
            return (parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return None
