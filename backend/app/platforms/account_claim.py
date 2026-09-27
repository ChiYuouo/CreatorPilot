"""本地登录文件的账号认领码；不向 API 暴露 Cookie 内容。"""

from hashlib import sha256
from pathlib import Path
import re

COOKIE_DIR = Path(__file__).resolve().parents[2] / "vendor" / "social_auto_upload" / "cookies"


def account_claim_code(platform: str, account_name: str) -> str:
    from app.platforms.registry import get_adapter

    get_adapter(platform)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", account_name):
        raise ValueError("账号标识格式不正确")
    cookie_file = COOKIE_DIR / f"{platform}_{account_name}.json"
    if not cookie_file.is_file():
        raise FileNotFoundError("本机没有这个账号的登录文件，请先扫码登录")
    return sha256(cookie_file.read_bytes()).hexdigest()[:16]
