"""平台适配层。

架构约束（Adapter Pattern）：
- 业务层与 Publisher 不直接依赖具体平台；由 Registry 选择 Adapter
- 新平台实现 Adapter 后在 Registry 注册
"""

from abc import ABC, abstractmethod
from typing import Any


class LoginExpired(RuntimeError):
    """平台账号登录态失效，发布尚未开始，可以放心重新提交。"""


class PlatformAdapter(ABC):
    """平台适配器抽象基类。"""

    async def collect_works(self, account_name: str, *, max_pages: int = 10) -> dict[str, Any]:
        """返回可核实作品及可用累计指标；不支持的平台明确拒绝。"""
        raise NotImplementedError("该平台暂不支持作品数据回收")

    @abstractmethod
    async def login(self, account_name: str, *, headless: bool = False, qrcode_callback: Any = None) -> dict[str, Any]:
        """启动平台登录；有二维码时通过回调报告。"""
        raise NotImplementedError

    @abstractmethod
    async def check_login(self, account_name: str) -> bool:
        """检查登录态。"""
        raise NotImplementedError

    @abstractmethod
    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """发布内容到平台，返回平台侧的发布结果（含内容 ID 等）。"""
        raise NotImplementedError

    @abstractmethod
    async def fetch_metrics(self, content_id: str) -> dict[str, Any]:
        """回收指定内容的数据指标。"""
        raise NotImplementedError
