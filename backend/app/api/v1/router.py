"""v1 版本总路由。"""

from fastapi import APIRouter

from app.api.v1 import agent, analytics, auth, automation, publishing, users

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(agent.router, prefix="", tags=["agent"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(automation.router, prefix="/automation", tags=["automation"])
api_router.include_router(publishing.router, prefix="/publishing", tags=["publishing"])
