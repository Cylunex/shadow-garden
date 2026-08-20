# Shadow Garden

Shadow Garden 是 Shadow 系列的个人内容创作与数字花园。它把写作、整理、发布和长期维护放在
同一条内容链路中，让文章既能持续生长，也能稳定对外呈现。

## 理念

- 内容属于用户，发布只是内容生命周期的一个状态；
- 编辑体验保持轻量，服务端保证版本、权限和发布事实可靠；
- 与 Platform Identity、Asset 等共享能力集成，但不把业务内容交给 Platform 管理。

## 主要功能

- 文章创建、编辑、草稿与发布；
- 标签、归档、搜索和公开页面；
- OIDC 登录与管理权限；
- FastAPI API、Web 前端和 PostgreSQL 持久化；
- 图片与跨项目资产接入。

## 本地开发

前后端分别按各自依赖文件安装，实际数据库、OIDC 和 Asset 配置写入被忽略的本地环境文件。

```bash
cd server
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
```

## 文档

接口和项目结构以源码内 OpenAPI、迁移和测试为准；生产运维信息统一保存在仓库外。
