FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.local \
    && chown -R appuser:appuser /app

USER appuser

# 此镜像仅用于自动化任务；API 和发布浏览器在本机运行。
CMD ["celery", "-A", "app.tasks.celery_app:celery_app", "worker", "--loglevel=info", "-Q", "celery", "--concurrency=2"]
