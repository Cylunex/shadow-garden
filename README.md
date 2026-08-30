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
.venv/bin/python -m app.migrations upgrade
.venv/bin/uvicorn app.main:app --reload
```

升级环境必须先显式执行版本化迁移；应用启动只校验迁移头，不会临时修改表结构。文章发布按
草稿、预览、修订、发布与撤回留存版本/事件，管理端导出的 ZIP 包含 Markdown、资源清单与
哈希，可通过 `/api/export/verify` 在隔离临时目录验证恢复。Travel 与 Archive 只以稳定
`shadow://` 引用进入导出，不在 Garden 复制上游事实。

## 文档

接口和项目结构以源码内 OpenAPI、迁移和测试为准；生产运维信息统一保存在仓库外。
