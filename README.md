# Shadow Garden

Cylunex 的数字花园 —— 前后端完整的个人网站：博客、项目展示、日常记录与风景合集、美食分享和旅行记录，带管理后台，持续生长。

## 技术栈与功能

- **后端**：FastAPI；数据库双后端——本地开发/测试默认 SQLite（零依赖），生产配 `GARDEN_DB_URL` 走 PostgreSQL；Markdown 服务端渲染 + pygments 代码高亮
- **鉴权**：公开页面保持匿名，管理后台使用 Shadow Identity 原生 OIDC Authorization Code + PKCE；浏览器只保存 HttpOnly 会话 Cookie，内容 Agent 使用独立 Bearer
- **前端**：无构建的纯 HTML/CSS/JS，改完即部署；页面通过 `/api` 拉取内容；深色/浅色主题手动切换（默认跟随系统）
- **博客体验**：站内全文搜索、标签筛选、按年归档、目录 TOC、字数/阅读时长、浏览计数、上一篇/下一篇
- **花园数据**：`/stats/` 统计页——文章/字数/阅读/浇水/园龄等面板 + GitHub 风格的年度照料热力图 + 标签榜
- **浇水与漫步**：文章页匿名点赞（「给这篇浇水」，Redis 防刷每 IP 每天一次）；页脚「随便逛逛」随机跳一篇内容
- **图片**：美食照片、游记相册、正文 Markdown 插图（后台上传），全站点击图片放大（灯箱）
- **订阅与 SEO**：RSS（`/feed.xml`）、sitemap（`/sitemap.xml`）、robots.txt
- **数据自持**：后台一键导出全部内容 JSON；备份 = 拷 `server/data/` 目录
- **部署**：nginx 服静态页与上传图、反代 `/api` 与 feed/sitemap 到 uvicorn（systemd 托管），rsync 一键部署

## 结构

```
site/                        # 前端静态站（= 服务器 webroot）
  index.html                 # 首页：聚合各版块最新内容（/api/summary）
  blog/                      # 博客列表（搜索/归档）+ 文章页（post.html?slug=…）
  projects/  food/  travel/  # 项目 / 美食 / 旅行（trip.html?id=…）
  moments/                   # 日常（记录、风景、多图与合集）
  stats/                     # 花园数据（统计 + 照料热力图）
  about/                     # 关于页
  admin/                     # 管理后台（登录后增删改查全部内容）
  assets/                    # main.css + admin.css + js/garden.js + js/admin.js
server/                      # FastAPI 后端
  app/
    main.py                  # 入口：/api/summary、/api/preview、静态托管（本地开发用）
    config.py db.py auth.py rendering.py
    routers/                 # posts / projects / food / travel / about / uploads / auth
    seed.py                  # 示例数据：python -m app.seed
  tests/                     # pytest 接口测试
  .env.example               # 复制为 .env 填口令（不入库）
deploy/                      # nginx / systemd 配置示例
scripts/deploy.sh            # 一键部署（rsync 前端；可选同步后端并重启服务）
scripts/deploy.env.example   # 部署目标配置模板（真实值放 deploy.env，不入库）
```

## 本地开发

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # 填 GARDEN_ADMIN_PASSWORD
.venv/bin/python -m app.seed    # 可选：灌示例数据
.venv/bin/uvicorn app.main:app --reload --port 8300
```

打开 <http://localhost:8300>（uvicorn 本地直接托管 `site/`），后台在 `/admin/`。

跑测试：`.venv/bin/python -m pytest tests/`（默认 SQLite；设 `PG_TEST_URL` / `REDIS_TEST_URL` 可整体切到生产同款后端跑同一套用例）

## API 一览

| 路径 | 说明 |
| --- | --- |
| `GET /auth/login` `/auth/callback`，`POST /auth/logout` `/logout/all` | Shadow Identity OIDC 登录与退出 |
| `GET /api/auth/me` | 当前后台会话状态 |
| `GET/POST /api/posts`，`GET /api/posts/{slug}`，`PUT/DELETE /api/posts/{id}` | 博客（草稿/发布、标签、Markdown） |
| `GET/POST/PUT/DELETE /api/projects` | 项目（状态、排序、链接） |
| `GET/POST/PUT/DELETE /api/food` | 美食（评分、照片、地点） |
| `GET/POST/PUT/DELETE /api/trips`，`GET /api/trips/{id}` | 旅行（日期、相册、Markdown 游记） |
| `GET/POST/PUT/PATCH/DELETE /api/moments` | 日常（记录/风景、Markdown、多图、合集） |
| `GET/PUT /api/about` | 关于页（介绍 + 联系方式） |
| `POST /api/uploads` | 图片上传（jpg/png/gif/webp，默认 ≤8MB） |
| `GET /api/summary` | 首页聚合 |
| `GET /api/stats` | 花园数据（统计 + 热力图 + 标签榜） |
| `POST /api/posts/{slug}/water` | 给文章浇水（匿名点赞，Redis 防刷） |
| `GET /api/random` | 随便逛逛（302 随机跳转） |
| `GET /api/search?q=` | 全文搜索（已发布文章 + 游记） |
| `GET /api/export` | 全量内容导出（备份，需登录） |
| `POST /api/preview` | Markdown 预览（后台用） |
| `GET /feed.xml` `GET /sitemap.xml` | RSS 订阅与站点地图 |

文章详情（`GET /api/posts/{slug}`）额外返回字数、预计阅读时长、浏览数与上一篇/下一篇。

内容 Agent 可通过 `GARDEN_AGENT_TOKEN` 使用 Bearer 鉴权，新增或修改博客、
美食、旅行、日常记录与风景合集并上传图片；删除内容、项目管理和关于页修改仍只允许管理员会话。

浏览器写操作使用 OIDC 会话 Cookie，并校验规范 Origin；内容 Agent 写操作继续使用
`Authorization: Bearer <token>`，两类身份不会互相替代。

## 部署

首次：

1. `cp scripts/deploy.env.example scripts/deploy.env`，填 SSH 主机、webroot；要部署后端就再填 `DEPLOY_SERVER_DIR` / `DEPLOY_SERVICE`
2. 在 Shadow Identity 登记 `shadow-garden` OIDC client 和 `garden-admins` 组，客户端原始 secret 只写服务器受限文件
3. 服务器上按 `deploy/shadow-garden.service.example` 配好 systemd，nginx 参考 `deploy/nginx.conf.example`，代理 `/auth/`、`/healthz` 并只对内开放 `/readyz`

之后每次改动只需：

```bash
./scripts/deploy.sh
```

## 约定

- 前端无构建步骤：纯静态 HTML/CSS/JS；新版块 = 一个页面 + 一个路由 + 后台一个模块配置
- 服务器地址、域名、口令一律不入库，只存在于 `deploy.env`、`server/.env` 与服务器本身
- 内容数据都在 `GARDEN_DATA_DIR`（默认 `server/data/`）：`garden.db` + `uploads/`，备份拷这个目录即可
