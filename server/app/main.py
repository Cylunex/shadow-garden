"""Shadow Garden 后端入口。

本地开发（在 server/ 目录）：
    uvicorn app.main:app --reload --port 8300
生产环境由 nginx 托管 site/ 与 /uploads/，仅反代 /api/ 与 feed/sitemap；
uvicorn 同时挂载 site/ 是为了本地一条命令起整站。
"""
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from email.utils import format_datetime
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import require_admin
from .config import SITE_DIR, settings
from .db import get_db, init_db, tags_from_json
from .rendering import render_markdown
from .routers import about, auth, food, moments, posts, projects, travel, uploads

SITE_TITLE = "Shadow Garden"
SITE_DESC = "Cylunex 的数字花园：博客、项目、美食与旅行"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Shadow Garden API", lifespan=lifespan)

for router in (auth.router, posts.router, projects.router, food.router,
               travel.router, moments.router, about.router, uploads.router):
    app.include_router(router)


@app.get("/api/summary")
def summary(conn: sqlite3.Connection = Depends(get_db)):
    """首页一次拉齐各版块最新内容。"""
    post_rows = conn.execute(
        "SELECT * FROM posts WHERE status = 'published' ORDER BY published_at DESC LIMIT 5"
    ).fetchall()
    project_rows = conn.execute(
        "SELECT * FROM projects ORDER BY sort_order DESC, created_at DESC LIMIT 6"
    ).fetchall()
    food_rows = conn.execute(
        "SELECT * FROM food ORDER BY CASE WHEN eaten_on = '' THEN created_at ELSE eaten_on END DESC LIMIT 4"
    ).fetchall()
    trip_rows = conn.execute(
        "SELECT * FROM trips ORDER BY CASE WHEN start_date = '' THEN created_at ELSE start_date END DESC LIMIT 3"
    ).fetchall()
    moment_rows = conn.execute(
        "SELECT * FROM moments ORDER BY created_at DESC, id DESC LIMIT 3"
    ).fetchall()
    return {
        "posts": [posts._serialize(r) for r in post_rows],
        "projects": [projects._serialize(r) for r in project_rows],
        "food": [food._serialize(r) for r in food_rows],
        "trips": [travel._serialize(r) for r in trip_rows],
        "moments": [moments._serialize(r) for r in moment_rows],
    }


@app.get("/api/search")
def search(
    q: str = Query(default="", max_length=80),
    conn: sqlite3.Connection = Depends(get_db),
):
    """站内搜索：已发布文章 + 游记，LIKE 匹配标题/摘要/正文。"""
    q = q.strip()
    if not q:
        return {"posts": [], "trips": []}
    like = "%" + q.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_") + "%"
    post_rows = conn.execute(
        r"""SELECT slug, title, summary, published_at, tags FROM posts
            WHERE status = 'published'
              AND (title LIKE ? ESCAPE '\' OR summary LIKE ? ESCAPE '\' OR content_md LIKE ? ESCAPE '\')
            ORDER BY published_at DESC LIMIT 20""",
        (like, like, like),
    ).fetchall()
    trip_rows = conn.execute(
        r"""SELECT id, title, destination, summary, start_date FROM trips
            WHERE title LIKE ? ESCAPE '\' OR summary LIKE ? ESCAPE '\' OR content_md LIKE ? ESCAPE '\'
            ORDER BY start_date DESC LIMIT 20""",
        (like, like, like),
    ).fetchall()
    return {
        "posts": [
            {"slug": r["slug"], "title": r["title"], "summary": r["summary"],
             "published_at": r["published_at"], "tags": tags_from_json(r["tags"])}
            for r in post_rows
        ],
        "trips": [dict(r) for r in trip_rows],
    }


def _base_url(request: Request) -> str:
    """站点根地址；nginx 反代时以 X-Forwarded-Proto + Host 为准。"""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _rfc822(iso: str) -> str:
    try:
        return format_datetime(datetime.fromisoformat(iso))
    except (TypeError, ValueError):
        return ""


@app.get("/feed.xml")
def feed(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    base = _base_url(request)
    rows = conn.execute(
        "SELECT * FROM posts WHERE status = 'published' ORDER BY published_at DESC LIMIT 20"
    ).fetchall()
    items = []
    for r in rows:
        link = f"{base}/blog/post.html?slug={quote(r['slug'])}"
        items.append(
            "<item>"
            f"<title>{escape(r['title'])}</title>"
            f"<link>{escape(link)}</link>"
            f'<guid isPermaLink="false">{escape(link)}</guid>'
            f"<pubDate>{_rfc822(r['published_at'])}</pubDate>"
            f"<description><![CDATA[{r['content_html']}]]></description>"
            "</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0">'
        "<channel>"
        f"<title>{escape(SITE_TITLE)}</title>"
        f"<link>{escape(base + '/')}</link>"
        f"<description>{escape(SITE_DESC)}</description>"
        "<language>zh-cn</language>"
        + "".join(items) +
        "</channel></rss>"
    )
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/sitemap.xml")
def sitemap(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    base = _base_url(request)
    urls = [f"{base}{p}" for p in
            ("/", "/blog/", "/projects/", "/food/", "/travel/", "/moments/", "/about/")]
    urls += [
        f"{base}/blog/post.html?slug={quote(r['slug'])}"
        for r in conn.execute("SELECT slug FROM posts WHERE status = 'published'")
    ]
    urls += [
        f"{base}/travel/trip.html?id={r['id']}"
        for r in conn.execute("SELECT id FROM trips")
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{escape(u)}</loc></url>" for u in urls) +
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/api/export", dependencies=[Depends(require_admin)])
def export_all(conn: sqlite3.Connection = Depends(get_db)):
    """一键导出全部内容（JSON），备份用。"""
    def dump(table: str):
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]

    return {
        "site": SITE_TITLE,
        "posts": dump("posts"),
        "projects": dump("projects"),
        "food": dump("food"),
        "trips": dump("trips"),
        "moments": dump("moments"),
        "about": dump("about"),
    }


class PreviewIn(BaseModel):
    content_md: str = ""


@app.post("/api/preview", dependencies=[Depends(require_admin)])
def preview(body: PreviewIn):
    return {"content_html": render_markdown(body.content_md)}


# 本地开发时由 uvicorn 直接提供上传图与静态站（生产环境交给 nginx）
@app.get("/uploads/{name}")
def serve_upload(name: str):
    path = settings.uploads_dir / name
    if name.startswith(".") or not path.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path)


if SITE_DIR.is_dir():
    app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
