"""本机扫码登录会话：只向所属用户返回临时二维码，不持久化凭证。"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AppError
from app.platforms.registry import get_platform
from app.platforms.runner import QRCODE_PREFIX, RESULT_PREFIX, RUNNER_ARGS

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SESSION_TTL_SECONDS = 15 * 60
LOGIN_TIMEOUT_SECONDS = 6 * 60
QR_CONFIRM_HINT_SECONDS = 45


@dataclass
class LoginSession:
    id: str
    user_id: int
    platform: str
    account_name: str
    remark: str | None
    existing_account_id: int | None
    created_at: float = field(default_factory=time.monotonic)
    status: str = "starting"
    qrcode_data_url: str | None = None
    qrcode_ready_at: float | None = None
    message: str | None = None
    account_id: int | None = None
    task: asyncio.Task[None] | None = None
    bind_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_sessions: dict[str, LoginSession] = {}


def _prune_sessions() -> None:
    now = time.monotonic()
    for session_id, session in list(_sessions.items()):
        if now - session.created_at > SESSION_TTL_SECONDS:
            if session.task and not session.task.done():
                session.task.cancel()
            del _sessions[session_id]


def start_login(user_id: int, platform: str, account_name: str,
                remark: str | None = None, existing_account_id: int | None = None) -> LoginSession:
    get_platform(platform)
    _prune_sessions()
    if any(item.user_id == user_id and item.platform == platform and
           item.account_name == account_name and item.status not in ("cancelled", "failed", "success")
           and item.task and not item.task.done()
           for item in _sessions.values()):
        raise AppError(409, "login_in_progress", "这个账号已有扫码登录正在进行")
    session = LoginSession(id=uuid.uuid4().hex, user_id=user_id, platform=platform,
                           account_name=account_name, remark=remark,
                           existing_account_id=existing_account_id)
    _sessions[session.id] = session
    session.task = asyncio.create_task(_run_login(session))
    return session


def get_login(session_id: str, user_id: int) -> LoginSession:
    _prune_sessions()
    session = _sessions.get(session_id)
    if session is None or session.user_id != user_id:
        raise AppError(404, "login_session_not_found", "扫码会话不存在或已过期")
    return session


def cancel_login(session_id: str, user_id: int) -> None:
    session = get_login(session_id, user_id)
    if session.task and not session.task.done():
        session.task.cancel()
    session.status = "cancelled"
    session.qrcode_data_url = None


async def _run_login(session: LoginSession) -> None:
    process: asyncio.subprocess.Process | None = None
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = await asyncio.create_subprocess_exec(
            settings.publisher_python, *RUNNER_ARGS,
            cwd=BACKEND_ROOT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=2 * 1024 * 1024,
            creationflags=creationflags,
        )
        request = {"action": "login", "platform": session.platform, "account_name": session.account_name}
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(request).encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()
        session.status = "waiting"
        if session.platform == "bilibili":
            session.message = "已打开 B 站扫码终端，请在终端中扫码登录"
        else:
            session.message = f"已打开浏览器窗口，请用{get_platform(session.platform).name} App 扫码登录"

        async def collect() -> dict | None:
            # 浏览器窗口对用户可见，扫码在窗口里完成；二维码只是顺手透传，拿不到不影响登录。
            result = None
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded.startswith(QRCODE_PREFIX):
                    payload = json.loads(decoded[len(QRCODE_PREFIX):])
                    image = payload.get("image_data_url", "")
                    if isinstance(image, str) and image.startswith((
                        "data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,",
                    )) and len(image) <= 1024 * 1024:
                        session.qrcode_data_url = image
                        session.qrcode_ready_at = time.monotonic()
                        session.status = "qrcode_ready"
                elif decoded.startswith(RESULT_PREFIX):
                    result = json.loads(decoded[len(RESULT_PREFIX):])
            await process.wait()
            return result

        result = await asyncio.wait_for(collect(), timeout=LOGIN_TIMEOUT_SECONDS)
        if process.returncode == 0 and isinstance(result, dict) and result.get("success") is True:
            session.status = "success"
            session.message = "扫码登录成功"
        else:
            session.status = "failed"
            session.message = str(result.get("message", "扫码登录失败") if isinstance(result, dict) else "扫码登录未返回结果")[:200]
            session.qrcode_data_url = None
    except asyncio.CancelledError:
        session.status = "cancelled"
        session.qrcode_data_url = None
        raise
    except TimeoutError:
        session.status = "failed"
        session.message = "扫码等待超时，请重新发起登录"
        session.qrcode_data_url = None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        session.status = "failed"
        session.message = f"登录运行环境异常：{str(exc)[:100]}"
        session.qrcode_data_url = None
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
