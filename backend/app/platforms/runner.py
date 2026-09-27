"""用 Python 3.12 独立进程调用 vendored 平台代码。输入仅来自本机服务。"""

from __future__ import annotations

import asyncio
import json
import sys

from app.platforms.registry import get_adapter

RESULT_PREFIX = "CREATORPILOT_RESULT="
QRCODE_PREFIX = "CREATORPILOT_QRCODE="
RUNNER_ARGS = ("-X", "utf8", "-m", "app.platforms.runner")


async def main() -> None:
    request = json.loads(sys.stdin.read())
    adapter = get_adapter(request["platform"])
    action = request["action"]
    if action == "check":
        result = {"valid": await adapter.check_login(request["account_name"])}
    elif action == "login":
        async def on_qrcode(payload: dict) -> None:
            print(QRCODE_PREFIX + json.dumps({"image_data_url": payload.get("image_data_url", "")}), flush=True)

        # 有头运行：平台登录页直接弹给用户，扫码在真实浏览器窗口里完成
        result = await adapter.login(request["account_name"], headless=False, qrcode_callback=on_qrcode)
    elif action == "publish":
        result = await adapter.publish(request["content"])
    elif action == "collect_works":
        from app.platforms.metrics_common import CollectionError
        try:
            result = await adapter.collect_works(request["account_name"], max_pages=request["max_pages"])
        except CollectionError as exc:
            result = {"status": "failed", "message": str(exc)}
    else:
        raise ValueError("未知发布操作")
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
