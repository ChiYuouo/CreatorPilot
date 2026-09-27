"""用户相关 DTO。"""

from datetime import datetime

from pydantic import BaseModel


class UserRead(BaseModel):
    id: int
    email: str
    nickname: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
