"""Shadow Garden 后端入口。

本地开发（在 server/ 目录）：
    uvicorn app.main:app --reload --port 8300
生产环境由 nginx 托管 site/ 与 /uploads/，反代 /api/、/auth/、探活与 feed/sitemap；
uvicorn 同时挂载 site/ 是为了本地一条命令起整站。
"""
import random
import sqlite3
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime
from email.utils import format_datetime
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import get_redis, require_admin, require_content_editor
from .config import SITE_DIR, settings
from .db import connect, get_db, init_db, tags_from_json
from .rendering import render_markdown, word_count
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


@app.get("/healthz")
def healthz():
    """Public liveness endpoint without dependency access."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Internal readiness endpoint for database and Redis dependencies."""
    database_ready = False
    redis_ready = False
    connection = None
    try:
        connection = connect()
        connection.execute("SELECT 1")
        database_ready = True
    except Exception:
        pass
    finally:
        if connection is not None:
            connection.close()
    try:
        redis_client = get_redis()
        redis_ready = redis_client is None or bool(redis_client.ping())
    except Exception:
        pass
    ready = database_ready and redis_ready
    return JSONResponse(
        {"status": "ready" if ready else "unavailable"},
        status_code=200 if ready else 503,
    )


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
    # lower() 两侧：SQLite 的 LIKE 本身不分大小写，PG 分——统一行为
    like = "%" + q.lower().replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_") + "%"
    post_rows = conn.execute(
        r"""SELECT slug, title, summary, published_at, tags FROM posts
            WHERE status = 'published'
              AND (lower(title) LIKE ? ESCAPE '\' OR lower(summary) LIKE ? ESCAPE '\'
                   OR lower(content_md) LIKE ? ESCAPE '\')
            ORDER BY published_at DESC LIMIT 20""",
        (like, like, like),
    ).fetchall()
    trip_rows = conn.execute(
        r"""SELECT id, title, destination, summary, start_date FROM trips
            WHERE lower(title) LIKE ? ESCAPE '\' OR lower(summary) LIKE ? ESCAPE '\'
                  OR lower(content_md) LIKE ? ESCAPE '\'
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


@app.get("/api/stats")
def stats(conn: sqlite3.Connection = Depends(get_db)):
    """花园数据：统计面板 + 过去一年的照料热力图 + 标签榜。"""
    def one(sql: str):
        return conn.execute(sql).fetchone()

    counts = {
        "posts": one("SELECT COUNT(*) AS n FROM posts WHERE status = 'published'")["n"],
        "moments": one("SELECT COUNT(*) AS n FROM moments")["n"],
        "food": one("SELECT COUNT(*) AS n FROM food")["n"],
        "trips": one("SELECT COUNT(*) AS n FROM trips")["n"],
        "projects": one("SELECT COUNT(*) AS n FROM projects")["n"],
    }

    words = 0
    for sql in (
        "SELECT content_md AS c FROM posts WHERE status = 'published'",
        "SELECT content_md AS c FROM trips",
        "SELECT content_md AS c FROM moments",
    ):
        words += sum(word_count(r["c"]) for r in conn.execute(sql))

    totals = one("SELECT COALESCE(SUM(views), 0) AS v, COALESCE(SUM(waters), 0) AS w FROM posts")
    rating = one("SELECT AVG(rating) AS a FROM food")["a"]

    # 照料热力图：各表内容按创建日期聚合（文章按发布日期）
    heat = Counter()
    for sql in (
        "SELECT substr(published_at, 1, 10) AS d FROM posts WHERE status = 'published'",
        "SELECT substr(created_at, 1, 10) AS d FROM moments",
        "SELECT substr(created_at, 1, 10) AS d FROM food",
        "SELECT substr(created_at, 1, 10) AS d FROM trips",
        "SELECT substr(created_at, 1, 10) AS d FROM projects",
    ):
        heat.update(r["d"] for r in conn.execute(sql) if r["d"])

    first = None
    for table, col in (("posts", "created_at"), ("moments", "created_at"),
                       ("food", "created_at"), ("trips", "created_at"),
                       ("projects", "created_at")):
        row = one(f"SELECT MIN({col}) AS m FROM {table}")
        if row["m"] and (first is None or row["m"] < first):
            first = row["m"]
    age_days = (date.today() - date.fromisoformat(first[:10])).days + 1 if first else 0

    tag_counter = Counter()
    for sql in ("SELECT tags FROM posts WHERE status = 'published'",
                "SELECT tags FROM food", "SELECT tags FROM projects"):
        for r in conn.execute(sql):
            tag_counter.update(tags_from_json(r["tags"]))

    return {
        "counts": counts,
        "words": words,
        "total_views": totals["v"],
        "total_waters": totals["w"],
        "avg_food_rating": round(float(rating), 1) if rating is not None else None,
        "garden_age_days": age_days,
        "heatmap": [{"date": d, "count": n} for d, n in sorted(heat.items())],
        "top_tags": [{"tag": t, "count": n} for t, n in tag_counter.most_common(20)],
    }


@app.get("/api/editor/context", dependencies=[Depends(require_content_editor)])
def editor_context(conn: sqlite3.Connection = Depends(get_db)):
    """给管理端与内容 Agent 的轻量工作上下文，不返回任何凭据。"""
    def count(sql: str) -> int:
        return conn.execute(sql).fetchone()["n"]

    draft_rows = conn.execute(
        """SELECT * FROM posts WHERE status = 'draft'
           ORDER BY updated_at DESC, id DESC LIMIT 10"""
    ).fetchall()
    recent_rows = conn.execute(
        """SELECT * FROM posts ORDER BY updated_at DESC, id DESC LIMIT 6"""
    ).fetchall()
    recent_daily_rows = conn.execute(
        """SELECT * FROM moments ORDER BY updated_at DESC, id DESC LIMIT 6"""
    ).fetchall()
    daily_collection_counts = Counter(
        name
        for row in conn.execute("SELECT * FROM moments")
        for name in moments._serialize(row)["collections"]
    )
    return {
        "agent_configured": bool(settings.agent_token),
        "counts": {
            "posts": count("SELECT COUNT(*) AS n FROM posts"),
            "drafts": count("SELECT COUNT(*) AS n FROM posts WHERE status = 'draft'"),
            "projects": count("SELECT COUNT(*) AS n FROM projects"),
            "food": count("SELECT COUNT(*) AS n FROM food"),
            "trips": count("SELECT COUNT(*) AS n FROM trips"),
            "moments": count("SELECT COUNT(*) AS n FROM moments"),
        },
        "drafts": [posts._serialize(row) for row in draft_rows],
        "recent_posts": [posts._serialize(row) for row in recent_rows],
        "recent_daily": [moments._serialize(row) for row in recent_daily_rows],
        "daily_collections": [
            {"name": name, "count": count}
            for name, count in daily_collection_counts.most_common()
        ],
        "capabilities": {
            "create": ["posts", "trips", "food", "moments", "uploads"],
            "update": ["posts", "trips", "food", "moments"],
            "delete": [],
            "restricted": ["projects", "about", "admin"],
        },
    }


@app.get("/api/random")
def random_walk(conn: sqlite3.Connection = Depends(get_db)):
    """随便逛逛：随机跳到花园里的一篇内容。"""
    urls = [
        f"/blog/post.html?slug={quote(r['slug'])}"
        for r in conn.execute("SELECT slug FROM posts WHERE status = 'published'")
    ]
    urls += [f"/travel/trip.html?id={r['id']}" for r in conn.execute("SELECT id FROM trips")]
    if conn.execute("SELECT COUNT(*) AS n FROM moments").fetchone()["n"]:
        urls.append("/moments/")
    if conn.execute("SELECT COUNT(*) AS n FROM food").fetchone()["n"]:
        urls.append("/food/")
    return RedirectResponse(random.choice(urls) if urls else "/", status_code=302)


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
            ("/", "/blog/", "/projects/", "/food/", "/travel/", "/moments/", "/stats/", "/about/")]
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
