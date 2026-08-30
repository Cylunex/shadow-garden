"""Shadow Garden 后端入口。

本地开发（在 server/ 目录）：
    uvicorn app.main:app --reload --port 8300
生产环境由 nginx 托管 site/ 与 /uploads/，反代 /api/、/auth/、探活与 feed/sitemap；
uvicorn 同时挂载 site/ 是为了本地一条命令起整站。
"""
import hashlib
import json
import random
import sqlite3
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing_extensions import Literal

from .auth import content_owner_id, get_redis, require_admin, require_content_editor
from .config import SITE_DIR, settings
from .db import connect, get_db, require_schema_current, tags_from_json
from .operation_context import OperationContext
from .portable import build_portable_bundle, verify_portable_bundle
from .rendering import render_markdown, word_count
from .content_health import validate_post
from .routers import about, auth, food, machine, moments, posts, projects, travel, uploads

SITE_TITLE = "Shadow Garden"
SITE_DESC = "Cylunex 的数字花园：博客、项目、美食与旅行"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_asset_config()
    require_schema_current()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Shadow Garden API", lifespan=lifespan)


@app.middleware("http")
async def operation_context(request: Request, call_next):
    context = OperationContext.from_request(request)
    request.state.operation_context = context
    response = await call_next(request)
    for name, value in context.headers().items():
        response.headers[name] = value
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

for router in (auth.router, machine.router, posts.router, projects.router, food.router,
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
def summary(owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    """首页一次拉齐各版块最新内容。"""
    post_rows = conn.execute(
        "SELECT * FROM posts WHERE owner_id=? AND status='published' ORDER BY published_at DESC LIMIT 5",
        (owner_id,),
    ).fetchall()
    project_rows = conn.execute(
        "SELECT * FROM projects WHERE owner_id=? ORDER BY sort_order DESC, created_at DESC LIMIT 6",
        (owner_id,),
    ).fetchall()
    food_rows = conn.execute(
        "SELECT * FROM food WHERE owner_id=? ORDER BY CASE WHEN eaten_on = '' THEN created_at ELSE eaten_on END DESC LIMIT 4",
        (owner_id,),
    ).fetchall()
    trip_rows = conn.execute(
        "SELECT * FROM trips WHERE owner_id=? ORDER BY CASE WHEN start_date = '' THEN created_at ELSE start_date END DESC LIMIT 3",
        (owner_id,),
    ).fetchall()
    moment_rows = conn.execute(
        "SELECT * FROM moments WHERE owner_id=? ORDER BY created_at DESC, id DESC LIMIT 3",
        (owner_id,),
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
    owner_id: str = Depends(content_owner_id),
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
            WHERE owner_id=? AND status = 'published'
              AND (lower(title) LIKE ? ESCAPE '\' OR lower(summary) LIKE ? ESCAPE '\'
                   OR lower(content_md) LIKE ? ESCAPE '\')
            ORDER BY published_at DESC LIMIT 20""",
        (owner_id, like, like, like),
    ).fetchall()
    trip_rows = conn.execute(
        r"""SELECT id, title, destination, summary, start_date FROM trips
            WHERE owner_id=? AND (lower(title) LIKE ? ESCAPE '\' OR lower(summary) LIKE ? ESCAPE '\'
                  OR lower(content_md) LIKE ? ESCAPE '\')
            ORDER BY start_date DESC LIMIT 20""",
        (owner_id, like, like, like),
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
def stats(owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    """花园数据：统计面板 + 过去一年的照料热力图 + 标签榜。"""
    def one(sql: str):
        return conn.execute(sql, (owner_id,)).fetchone()

    counts = {
        "posts": one("SELECT COUNT(*) AS n FROM posts WHERE owner_id=? AND status='published'")["n"],
        "moments": one("SELECT COUNT(*) AS n FROM moments WHERE owner_id=?")["n"],
        "food": one("SELECT COUNT(*) AS n FROM food WHERE owner_id=?")["n"],
        "trips": one("SELECT COUNT(*) AS n FROM trips WHERE owner_id=?")["n"],
        "projects": one("SELECT COUNT(*) AS n FROM projects WHERE owner_id=?")["n"],
    }

    words = 0
    for sql in (
        "SELECT content_md AS c FROM posts WHERE owner_id=? AND status='published'",
        "SELECT content_md AS c FROM trips WHERE owner_id=?",
        "SELECT content_md AS c FROM moments WHERE owner_id=?",
    ):
        words += sum(word_count(r["c"]) for r in conn.execute(sql, (owner_id,)))

    totals = one("SELECT COALESCE(SUM(views),0) AS v,COALESCE(SUM(waters),0) AS w FROM posts WHERE owner_id=?")
    rating = one("SELECT AVG(rating) AS a FROM food WHERE owner_id=?")["a"]

    # 照料热力图：各表内容按创建日期聚合（文章按发布日期）
    heat = Counter()
    for sql in (
        "SELECT substr(published_at,1,10) AS d FROM posts WHERE owner_id=? AND status='published'",
        "SELECT substr(created_at,1,10) AS d FROM moments WHERE owner_id=?",
        "SELECT substr(created_at,1,10) AS d FROM food WHERE owner_id=?",
        "SELECT substr(created_at,1,10) AS d FROM trips WHERE owner_id=?",
        "SELECT substr(created_at,1,10) AS d FROM projects WHERE owner_id=?",
    ):
        heat.update(r["d"] for r in conn.execute(sql, (owner_id,)) if r["d"])

    first = None
    for table, col in (("posts", "created_at"), ("moments", "created_at"),
                       ("food", "created_at"), ("trips", "created_at"),
                       ("projects", "created_at")):
        row = one(f"SELECT MIN({col}) AS m FROM {table} WHERE owner_id=?")
        if row["m"] and (first is None or row["m"] < first):
            first = row["m"]
    age_days = (date.today() - date.fromisoformat(first[:10])).days + 1 if first else 0

    tag_counter = Counter()
    for sql in ("SELECT tags FROM posts WHERE owner_id=? AND status='published'",
                "SELECT tags FROM food WHERE owner_id=?", "SELECT tags FROM projects WHERE owner_id=?"):
        for r in conn.execute(sql, (owner_id,)):
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
def editor_context(owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    """给管理端与内容 Agent 的轻量工作上下文，不返回任何凭据。"""
    def count(sql: str) -> int:
        return conn.execute(sql, (owner_id,)).fetchone()["n"]

    draft_rows = conn.execute(
        """SELECT * FROM posts WHERE owner_id=? AND status IN ('draft','preview','revision')
           ORDER BY updated_at DESC, id DESC LIMIT 10""", (owner_id,)
    ).fetchall()
    recent_rows = conn.execute(
        """SELECT * FROM posts WHERE owner_id=? ORDER BY updated_at DESC, id DESC LIMIT 6""", (owner_id,)
    ).fetchall()
    recent_daily_rows = conn.execute(
        """SELECT * FROM moments WHERE owner_id=? ORDER BY updated_at DESC, id DESC LIMIT 6""", (owner_id,)
    ).fetchall()
    daily_collection_counts = Counter(
        name
        for row in conn.execute("SELECT * FROM moments WHERE owner_id=?", (owner_id,))
        for name in moments._serialize(row)["collections"]
    )
    return {
        "agent_configured": bool(settings.agent_token),
        "counts": {
            "posts": count("SELECT COUNT(*) AS n FROM posts WHERE owner_id=?"),
            "drafts": count("SELECT COUNT(*) AS n FROM posts WHERE owner_id=? AND status IN ('draft','preview','revision')"),
            "projects": count("SELECT COUNT(*) AS n FROM projects WHERE owner_id=?"),
            "food": count("SELECT COUNT(*) AS n FROM food WHERE owner_id=?"),
            "trips": count("SELECT COUNT(*) AS n FROM trips WHERE owner_id=?"),
            "moments": count("SELECT COUNT(*) AS n FROM moments WHERE owner_id=?"),
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


class SuggestionFeedback(BaseModel):
    action: Literal["dismiss", "snooze"]


def _suggestion_id(owner_id: str, subject_uri: str, kind: str) -> str:
    digest = hashlib.sha256(f"{owner_id}\0{subject_uri}\0{kind}".encode()).hexdigest()
    return f"suggestion-{digest[:32]}"


@app.get("/api/editor/suggestions", dependencies=[Depends(require_admin)])
def editor_suggestions(
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    """At most five quiet, evidence-backed reminders; never a publishing quota."""
    now = datetime.now(timezone.utc)
    draft_cutoff = (now - timedelta(days=14)).isoformat(timespec="seconds")
    revisit_cutoff = (now - timedelta(days=180)).isoformat(timespec="seconds")
    candidates: list[dict[str, str]] = []
    for row in conn.execute(
        """SELECT id,title,status,updated_at FROM posts
           WHERE owner_id=? AND status IN ('draft','revision') AND updated_at<=?
           ORDER BY updated_at LIMIT 5""",
        (owner_id, draft_cutoff),
    ):
        candidates.append(
            {
                "kind": "stale-draft", "subject_uri": f"shadow://garden/posts/{row['id']}",
                "title": row["title"], "reason": f"这篇{row['status']}自 {row['updated_at'][:10]} 后没有变动",
                "allowed_actions": ["open", "dismiss", "snooze"],
            }
        )
    if len(candidates) < 5:
        for row in conn.execute(
            """SELECT id,title,updated_at FROM posts
               WHERE owner_id=? AND status='published' AND updated_at<=?
               AND (rediscover_after IS NULL OR rediscover_after<=?)
               ORDER BY updated_at LIMIT ?""",
            (owner_id, revisit_cutoff, now.isoformat(timespec="seconds"), 5 - len(candidates)),
        ):
            candidates.append(
                {
                    "kind": "gentle-revisit", "subject_uri": f"shadow://garden/posts/{row['id']}",
                    "title": row["title"], "reason": "半年未回看；只在你想重访时打开",
                    "allowed_actions": ["open", "dismiss", "snooze"],
                }
            )
    items = []
    for item in candidates:
        item["id"] = _suggestion_id(owner_id, item["subject_uri"], item["kind"])
        feedback = conn.execute(
            "SELECT state,snoozed_until FROM garden_suggestions WHERE id=? AND owner_id=?",
            (item["id"], owner_id),
        ).fetchone()
        if feedback and (
            feedback["state"] == "dismissed"
            or (feedback["snoozed_until"] and feedback["snoozed_until"] > now.isoformat())
        ):
            continue
        items.append(item)
    return {"items": items[:5], "pressure": "none", "generated_at": now_iso()}


@app.post("/api/editor/suggestions/{suggestion_id}", dependencies=[Depends(require_admin)])
def suggestion_feedback(
    suggestion_id: str,
    body: SuggestionFeedback,
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    if not suggestion_id.startswith("suggestion-") or len(suggestion_id) != 43:
        raise HTTPException(404, "回顾建议不存在")
    now = now_iso()
    state = "dismissed" if body.action == "dismiss" else "snoozed"
    snoozed = None if body.action == "dismiss" else (
        datetime.now(timezone.utc) + timedelta(days=30)
    ).isoformat(timespec="seconds")
    # Subject details are intentionally not accepted from the caller. A bounded opaque
    # record is enough to suppress a suggestion without creating a second content store.
    conn.execute(
        """INSERT INTO garden_suggestions
           (id,owner_id,subject_uri,kind,state,snoozed_until,created_at,updated_at)
           VALUES (?,?,?,'feedback',?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET state=?,snoozed_until=?,updated_at=?""",
        (
            suggestion_id, owner_id, f"shadow://garden/suggestions/{suggestion_id}",
            state, snoozed, now, now, state, snoozed, now,
        ),
    )
    return {"id": suggestion_id, "state": state, "snoozed_until": snoozed}


@app.get("/api/random")
def random_walk(owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    """随便逛逛：随机跳到花园里的一篇内容。"""
    urls = [
        f"/blog/post.html?slug={quote(r['slug'])}"
        for r in conn.execute("SELECT slug FROM posts WHERE owner_id=? AND status='published'", (owner_id,))
    ]
    urls += [f"/travel/trip.html?id={r['id']}" for r in conn.execute("SELECT id FROM trips WHERE owner_id=?", (owner_id,))]
    if conn.execute("SELECT COUNT(*) AS n FROM moments WHERE owner_id=?", (owner_id,)).fetchone()["n"]:
        urls.append("/moments/")
    if conn.execute("SELECT COUNT(*) AS n FROM food WHERE owner_id=?", (owner_id,)).fetchone()["n"]:
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
def feed(request: Request, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    base = _base_url(request)
    rows = conn.execute(
        "SELECT * FROM posts WHERE owner_id=? AND status='published' ORDER BY published_at DESC LIMIT 20",
        (owner_id,),
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
def sitemap(request: Request, owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    base = _base_url(request)
    urls = [f"{base}{p}" for p in
            ("/", "/blog/", "/projects/", "/food/", "/travel/", "/moments/", "/stats/", "/about/")]
    urls += [
        f"{base}/blog/post.html?slug={quote(r['slug'])}"
        for r in conn.execute("SELECT slug FROM posts WHERE owner_id=? AND status='published'", (owner_id,))
    ]
    urls += [
        f"{base}/travel/trip.html?id={r['id']}"
        for r in conn.execute("SELECT id FROM trips WHERE owner_id=?", (owner_id,))
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{escape(u)}</loc></url>" for u in urls) +
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/api/export", dependencies=[Depends(require_admin)])
def export_all(owner_id: str = Depends(content_owner_id), conn: sqlite3.Connection = Depends(get_db)):
    """Portable Markdown, resource inventory and trace history; no upstream facts."""
    bundle = build_portable_bundle(conn, owner_id)
    return Response(
        content=bundle,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=garden-portable.zip",
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/export/verify", dependencies=[Depends(require_admin)])
async def verify_export(file: UploadFile):
    limit = 256 * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "恢复包超过 256MB 验证上限")
    try:
        return verify_portable_bundle(data)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"隔离恢复验证失败：{exc}") from exc


class PreviewIn(BaseModel):
    title: str = "预览"
    content_md: str = ""
    source_refs: list[str] = []
    check_external: bool | None = None


@app.post("/api/preview", dependencies=[Depends(require_content_editor)])
def preview(
    body: PreviewIn,
    owner_id: str = Depends(content_owner_id),
    conn: sqlite3.Connection = Depends(get_db),
):
    return validate_post(
        conn,
        owner_id=owner_id,
        title=body.title,
        content_md=body.content_md,
        source_refs=body.source_refs,
        check_external=body.check_external,
    )


# 本地开发时由 uvicorn 直接提供上传图与静态站（生产环境交给 nginx）
@app.get("/uploads/{name}")
def serve_upload(name: str):
    root = settings.uploads_dir.resolve()
    path = (root / name).resolve()
    if name.startswith(".") or Path(name).name != name or not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path)


if SITE_DIR.is_dir():
    app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
