"""以独立 Python 3.12 环境运行 vendored 上传器。"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import settings
from app.platforms.runner import RESULT_PREFIX, RUNNER_ARGS

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class PublishCancelled(RuntimeError):
    """用户请求停止正在运行的本机发布进程。"""


class PublishTimeout(RuntimeError):
    """本机发布进程超过配置时限仍未返回结果。"""


async def _stop_process_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        killer = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(process.pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        await killer.wait()
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await process.wait()


async def _wait_for_cancel(check: Callable[[], Awaitable[bool]]) -> None:
    while True:
        if await check():
            return
        await asyncio.sleep(2)


async def run_publisher(action: str, *, cancel_requested: Callable[[], Awaitable[bool]] | None = None,
                        **payload: Any) -> dict[str, Any]:
    if cancel_requested and await cancel_requested():
        raise PublishCancelled("发布任务已取消，未启动上传进程")
    try:
        process = await asyncio.create_subprocess_exec(
            settings.publisher_python, *RUNNER_ARGS,
            cwd=BACKEND_ROOT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}),
        )
    except OSError as exc:
        raise RuntimeError("发布运行环境不可用，请检查 PUBLISHER_PYTHON") from exc
    communication = asyncio.create_task(process.communicate(json.dumps({"action": action, **payload}, ensure_ascii=False).encode("utf-8")))
    monitor = asyncio.create_task(_wait_for_cancel(cancel_requested)) if cancel_requested else None
    try:
        timeout = (settings.publish_timeout_seconds if action == "publish" else
                   settings.metrics_sync_timeout_seconds if action == "collect_works" else 120)
        done, _ = await asyncio.wait(
            {communication, monitor} if monitor else {communication},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            raise PublishTimeout(
                f"平台操作超过 {timeout} 秒未完成，本机进程已自动停止"
            )
        if monitor and monitor in done:
            await monitor
            raise PublishCancelled("发布进程已按取消请求停止，平台结果仍需核实")
        stdout, stderr = await communication
    finally:
        if monitor:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
        if process.returncode is None:
            await _stop_process_tree(process)
        if not communication.done():
            communication.cancel()
            await asyncio.gather(communication, return_exceptions=True)
    if process.returncode != 0:
        raise RuntimeError("平台操作失败，请检查发布服务日志和平台登录态")
    line = next((line for line in reversed(stdout.decode("utf-8", errors="replace").splitlines()) if line.startswith(RESULT_PREFIX)), None)
    if line is None:
        raise RuntimeError("平台操作未返回可识别结果，请到平台后台核实")
    return json.loads(line[len(RESULT_PREFIX):])


class SubprocessPublisher:
    async def publish(self, platform: str, content: dict[str, Any],
                      *, cancel_requested: Callable[[], Awaitable[bool]] | None = None) -> dict[str, Any]:
        return await run_publisher("publish", platform=platform, content=content, cancel_requested=cancel_requested)
