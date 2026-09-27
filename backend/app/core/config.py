"""全局配置。

所有配置集中在此，通过环境变量或 .env 文件覆盖。
业务代码禁止散落硬编码配置。
"""

from functools import lru_cache

from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creatorpilot:creatorpilot@localhost:5433/creatorpilot"
    redis_url: str = "redis://localhost:6380/0"
    celery_broker_url: str = ""  # 留空时复用 Redis 地址
    media_root: str = ".local/media"
    media_preview_expire_seconds: int = Field(default=900, ge=60, le=3600)
    publisher_python: str = "python"  # 本机运行时指向用于发布的 Python 3.12 虚拟环境
    publish_timeout_seconds: int = 300  # 单次平台上传的最长等待时间，超时后自动停止本机进程
    metrics_sync_timeout_seconds: int = Field(default=180, ge=30, le=1800)
    metrics_sync_max_pages: int = Field(default=10, ge=1, le=100)

    secret_key: str = "dev-secret-change-me-to-a-random-32-byte-key"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: str = "http://localhost:5173"

    # LLM（OpenAI 兼容协议，默认 DeepSeek）
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 120.0

    # 智能体配置
    agent_max_tool_rounds: int = 5
    agent_history_limit: int = 20  # 每次送入 Agent 的历史消息条数上限
    agent_session_ttl_seconds: int = 7 * 24 * 3600  # 会话短期记忆保留 7 天

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
