# 开发指南

本文面向修改 CreatorPilot 源码的开发者。应用介绍和日常使用见 [README](README.md)。

[准备环境](#准备环境) · [本地开发](#本地开发) · [后台任务](#后台任务) · [数据库迁移](#数据库迁移) · [提交前检查](#提交前检查)

## 准备环境

使用 Windows、Python 3.12、Node.js 22 LTS 和 Docker Desktop。完整发布登录流程目前依赖 Windows 可见浏览器或终端。

以下命令使用 PowerShell。准备环境时从仓库根目录开始，按顺序执行；每个安装步骤结束后会返回根目录。已经按 README 安装过依赖和初始化数据库，可直接进入 [本地开发](#本地开发)。

首次开发时，在仓库根目录创建配置：

```powershell
if (-not (Test-Path backend/.env)) {
    Copy-Item backend/.env.example backend/.env
}
py -3.12 -c "import secrets; print(secrets.token_hex(32))"
```

将随机值填入 `SECRET_KEY`；开发 AI 功能时填写模型配置。已有 `.env` 时直接复用，不要覆盖。

在仓库根目录启动基础服务：

```powershell
docker compose --env-file backend/.env up -d postgres redis
docker compose --env-file backend/.env ps
```

等待服务健康后，从仓库根目录安装后端并初始化数据库：

```powershell
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m alembic upgrade head
cd ..
```

在仓库根目录安装前端依赖：

```powershell
cd frontend
npm ci
cd ..
```

开发账号登录、发布和采集功能时，还需运行 README [安装后端与上传器](README.md#3-安装后端与上传器) 中的“上传器与浏览器”命令。仅开发页面与普通 API 时可以先不安装发布环境。

## 本地开发

### 后端

从仓库根目录打开终端：

```powershell
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

访问 [API 文档](http://localhost:8100/docs)。`pip install -e .` 使用源码安装，修改 Python 代码后由 Uvicorn 自动重新加载；修改依赖声明后需要重新安装。

后端从当前工作目录读取 `.env`，因此 API、Alembic 和本机 Worker 均应从 `backend/` 启动。

### 前端

另开终端，从仓库根目录执行：

```powershell
cd frontend
npm run dev
```

访问 [http://localhost:5173](http://localhost:5173)。Vite 自动更新修改后的页面，并将 `/api` 请求代理到 `http://127.0.0.1:8100`。

`npm run dev` 和 `npm start` 都使用 5173 端口，不能同时启动。开发模式无需提前构建；`npm start` 则需要先执行 `npm run build`。

## 后台任务

项目使用两个队列：

| 队列 | 任务 | 默认运行方式 |
| --- | --- | --- |
| `celery` | 分析报告、自动化分派与任务回收 | Docker Worker |
| `publishing` | 平台发布、作品指标采集 | 本机 Worker |

账号扫码会话由 API 直接启动上传器子进程，不经过 Worker。

### 发布与指标采集

在独立终端中，从仓库根目录执行：

```powershell
cd backend
.venv/Scripts/python.exe -m celery -A app.tasks.celery_app:celery_app worker --loglevel=info -Q publishing --pool=solo --concurrency=1
```

上传器运行在 `PUBLISHER_PYTHON` 指定的独立环境中。修改 `app/platforms/` 或任务代码后重启该 Worker；修改上传器依赖后更新 `.venv-publish`。

### 分析与自动化

不修改任务源码时，可以在仓库根目录启动 Docker 自动化服务：

```powershell
docker compose --env-file backend/.env --profile automation up -d --build worker beat
```

调试任务源码时，先在仓库根目录停止 Docker Worker 和 Beat，避免旧镜像消费任务：

```powershell
docker compose --env-file backend/.env --profile automation stop worker beat
```

然后在独立终端中，从仓库根目录启动本机分析 Worker：

```powershell
cd backend
.venv/Scripts/python.exe -m celery -A app.tasks.celery_app:celery_app worker --loglevel=info -Q celery --pool=solo --concurrency=1
```

调试每周计划、先同步再分析、等待同步结果的自动化任务或超时发布任务回收时，还需运行 Beat。它会周期性分派和检查任务；只启动 Worker 无法完成这些流程。

另开终端，从仓库根目录执行：

```powershell
cd backend
New-Item -ItemType Directory -Force .local | Out-Null
.venv/Scripts/python.exe -m celery -A app.tasks.celery_app:celery_app beat --loglevel=info --schedule=.local/celerybeat-schedule
```

只运行一个 Beat；Celery 没有自动重载，代码变化后手动重启 Worker 或 Beat。恢复 Docker 模式时，先停止本机分析 Worker 和 Beat。

## 项目结构

```text
backend/
├── app/
│   ├── api/v1/     # HTTP 接口
│   ├── schemas/    # 请求和响应的数据校验
│   ├── services/   # 业务逻辑
│   ├── models/     # 数据库模型
│   ├── agents/     # 智能体编排与工具
│   ├── llm/        # 模型调用
│   ├── tasks/      # 后台任务
│   └── platforms/  # 平台适配及上传器进程
├── alembic/        # 数据库迁移
└── vendor/         # 第三方上传器
frontend/
└── src/
    ├── pages/      # 页面
    ├── components/ # 通用组件
    ├── api/        # API 请求
    └── stores/     # 前端状态
```

新增 API 时，分别检查请求模型、业务服务、接口路由和前端调用。平台兼容逻辑优先放在 `app/platforms/`，减少对第三方上传器的直接修改。

模型调用统一经过 `app/llm/`，后台任务使用 `app/tasks/celery_app.py` 的队列配置。新增平台需在 `app/platforms/registry.py` 注册能力，页面使用同一份平台信息。

## 数据库迁移

修改 `backend/app/models/` 后，从 `backend/` 执行：

```powershell
.venv/Scripts/python.exe -m alembic revision --autogenerate -m "describe_change"
```

检查生成的迁移，尤其是列重命名、删除字段、数据转换和 `downgrade()`。确认后执行：

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
```

- 已发布的迁移保持不变，后续变更新增迁移文件。
- 迁移前备份数据，并停止可能访问相关表的任务进程。
- 新迁移应同时在空数据库和已有测试数据的数据库上验证。
- 当前初始化基线仅适用于新数据库，不可直接升级原项目旧数据库。

## 依赖管理

后端依赖在 `backend/pyproject.toml` 中声明，修改后从 `backend/` 执行：

```powershell
.venv/Scripts/python.exe -m pip install -e .
```

发布环境的安装入口是 `backend/requirements-publisher.txt`。从 `backend/` 更新上传器依赖：

```powershell
.venv-publish/Scripts/python.exe -m pip install -r requirements-publisher.txt
# Patchright 版本变化时重新安装对应浏览器。
.venv-publish/Scripts/patchright.exe install chromium
```

前端新增依赖时从 `frontend/` 执行 `npm install <package>`，同时提交 `package.json` 和 `package-lock.json`。已有依赖按锁文件安装使用 `npm ci`。

上传器的 `uv.lock` 是上游保留的锁文件，当前 pip 安装流程不读取它。不要将锁文件与临时构建产物一起清理。

Docker 自动化服务使用镜像内的代码，不会随本机源码热重载。后端依赖或任务代码变化后，在仓库根目录执行 `docker compose --env-file backend/.env --profile automation up -d --build worker beat`。本机开发模式则重新安装依赖并重启相关进程。

## 提交前检查

### 前端构建

从 `frontend/` 执行：

```powershell
npm run build
```

### 后端加载与迁移

确保测试数据库已启动，从 `backend/` 执行：

```powershell
.venv/Scripts/python.exe -c "from app.main import app; print(app.title)"
.venv/Scripts/python.exe -m alembic check
```

### Docker 配置

从仓库根目录执行：

```powershell
docker compose --env-file backend/.env --profile automation config --quiet
```

仓库目前没有完整的自动化测试套件。上述命令用于构建、加载与结构检查；提交前还需验证改动涉及的业务流程。例如认证变更应检查注册、登录和令牌刷新，素材变更应检查上传与预览，任务变更应检查执行状态和取消操作。

真实平台测试使用自己的测试账号，发布后在平台确认结果。提交说明应包含修改原因、验证方法，以及未完成的验证项。

## 文件与数据

| 类型 | 处理方式 |
| --- | --- |
| 源码、迁移、依赖声明、锁文件、环境模板 | 随修改提交 |
| `.env`、素材、账号 Cookie | 作为本机配置和使用数据保存，不提交 |
| 虚拟环境、依赖目录、构建产物、缓存、日志 | 自动生成，不提交 |

忽略规则见 [.gitignore](.gitignore)。清理 `build/`、`dist/` 或缓存后可以重新生成；`backend/.local/media/`、平台 Cookie 和 Docker 数据卷包含使用数据，清理前应确认并备份。

修改 `vendor/social_auto_upload/` 前阅读其 [说明](backend/vendor/social_auto_upload/README.md) 和 [许可证](backend/vendor/social_auto_upload/LICENSE)。记录兼容改动，更新上游代码时逐项核对。
