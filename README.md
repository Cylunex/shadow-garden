# Shadow Garden

Cylunex 的数字花园 —— 前后端完整的个人网站：博客、项目展示、说说、美食分享与旅行记录，带管理后台，持续生长。

## 技术栈与功能

- **后端**：FastAPI + SQLite（单文件数据库，数据自持），Markdown 服务端渲染 + pygments 代码高亮，口令登录 + Bearer 会话
- **前端**：无构建的纯 HTML/CSS/JS，改完即部署；页面通过 `/api` 拉取内容；深色/浅色主题手动切换（默认跟随系统）
- **博客体验**：站内全文搜索、标签筛选、按年归档、目录 TOC、字数/阅读时长、浏览计数、上一篇/下一篇
- **订阅与 SEO**：RSS（`/feed.xml`）、sitemap（`/sitemap.xml`）、robots.txt
- **数据自持**：后台一键导出全部内容 JSON；备份 = 拷 `server/data/` 目录
- **部署**：nginx 服静态页与上传图、反代 `/api` 与 feed/sitemap 到 uvicorn（systemd 托管），rsync 一键部署

## 结构

```
site/                        # 前端静态站（= 服务器 webroot）
  index.html                 # 首页：聚合各版块最新内容（/api/summary）
  blog/                      # 博客列表（搜索/归档）+ 文章页（post.html?slug=…）
  projects/  food/  travel/  # 项目 / 美食 / 旅行（trip.html?id=…）
  moments/                   # 说说（短内容随手记）
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

跑测试：`.venv/bin/python -m pytest tests/`

## API 一览

| 路径 | 说明 |
| --- | --- |
| `POST /api/auth/login` `/logout` `GET /api/auth/me` | 口令换会话 token（Bearer） |
| `GET/POST /api/posts`，`GET /api/posts/{slug}`，`PUT/DELETE /api/posts/{id}` | 博客（草稿/发布、标签、Markdown） |
| `GET/POST/PUT/DELETE /api/projects` | 项目（状态、排序、链接） |
| `GET/POST/PUT/DELETE /api/food` | 美食（评分、照片、地点） |
| `GET/POST/PUT/DELETE /api/trips`，`GET /api/trips/{id}` | 旅行（日期、相册、Markdown 游记） |
| `GET/POST/PUT/DELETE /api/moments` | 说说（短内容，Markdown） |
| `GET/PUT /api/about` | 关于页（介绍 + 联系方式） |
| `POST /api/uploads` | 图片上传（jpg/png/gif/webp，默认 ≤8MB） |
| `GET /api/summary` | 首页聚合 |
| `GET /api/search?q=` | 全文搜索（已发布文章 + 游记） |
| `GET /api/export` | 全量内容导出（备份，需登录） |
| `POST /api/preview` | Markdown 预览（后台用） |
| `GET /feed.xml` `GET /sitemap.xml` | RSS 订阅与站点地图 |

文章详情（`GET /api/posts/{slug}`）额外返回字数、预计阅读时长、浏览数与上一篇/下一篇。

写操作都要 `Authorization: Bearer <token>`。

## 部署

首次：

1. `cp scripts/deploy.env.example scripts/deploy.env`，填 SSH 主机、webroot；要部署后端就再填 `DEPLOY_SERVER_DIR` / `DEPLOY_SERVICE`
2. 服务器上按 `deploy/shadow-garden.service.example` 配好 systemd（口令写在 `/etc/shadow-garden.env`），nginx 参考 `deploy/nginx.conf.example`

之后每次改动只需：

```bash
./scripts/deploy.sh
```

## 约定

- 前端无构建步骤：纯静态 HTML/CSS/JS；新版块 = 一个页面 + 一个路由 + 后台一个模块配置
- 服务器地址、域名、口令一律不入库，只存在于 `deploy.env`、`server/.env` 与服务器本身
- 内容数据都在 `GARDEN_DATA_DIR`（默认 `server/data/`）：`garden.db` + `uploads/`，备份拷这个目录即可
