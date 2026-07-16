"""种子数据：python -m app.seed（在 server/ 目录）。只在对应表为空时插入。"""
from .db import connect, init_db, now_iso, tags_to_json
from .rendering import render_markdown

POSTS = [
    {
        "slug": "hello-world",
        "title": "Hello World：这座花园是怎么搭起来的",
        "summary": "从一台 ECS、一份 nginx 配置和一个 rsync 脚本开始，到现在的前后端小站。",
        "content_md": (
            "这座花园的第一版只有一张静态 HTML。后来它长出了后端：\n\n"
            "- **FastAPI + SQLite**：一个进程、一个数据库文件，数据自持\n"
            "- **无构建前端**：纯 HTML/CSS/JS，改完即部署\n"
            "- **rsync 一键部署**：`./scripts/deploy.sh`\n\n"
            "## 为什么不上现成的博客系统\n\n"
            "因为自己种的树，浇水才有意思。\n\n"
            "```bash\n./scripts/deploy.sh\n```\n"
        ),
        "tags": ["建站", "碎碎念"],
    },
    {
        "slug": "nginx-https-notes",
        "title": "给 nginx 配 HTTPS 的几个小坑",
        "summary": "证书续期、HTTP 跳转、反代头透传，一次记下来。",
        "content_md": (
            "记录几个踩过的坑：\n\n"
            "1. `certbot renew` 要配好 webroot，否则续期悄悄失败\n"
            "2. 反代给后端时记得带上 `X-Forwarded-Proto`，不然生成的链接是 http\n"
            "3. `client_max_body_size` 默认 1m，传图会 413\n"
        ),
        "tags": ["nginx", "运维"],
    },
]

PROJECTS = [
    {
        "name": "Shadow Health",
        "description": "个人健康与训练管理应用：跑步、力量循环、体测数据一站式记录与分析，自部署、数据自持。",
        "tags": ["Python", "PostgreSQL", "PWA"],
        "status": "active",
        "sort_order": 10,
    },
    {
        "name": "Shadow Garden",
        "description": "就是这个网站本身——FastAPI + SQLite 后端，无构建静态前端，一座慢慢生长的数字花园。",
        "tags": ["FastAPI", "SQLite", "nginx"],
        "status": "active",
        "sort_order": 9,
    },
]

FOOD = [
    {
        "title": "深夜的一碗牛肉面",
        "emoji": "🍜",
        "rating": 5,
        "location": "楼下面馆",
        "review": "汤浓、面弹、牛肉给得实在，加班后的救赎。",
        "tags": ["面食"],
        "eaten_on": "2026-07-10",
    },
    {
        "title": "第一次做的番茄炖牛腩",
        "emoji": "🥘",
        "rating": 4,
        "location": "自家厨房",
        "review": "炖了两个半小时，番茄放少了，下次翻倍。翻车边缘但值得记。",
        "tags": ["家常菜", "自己做"],
        "eaten_on": "2026-07-05",
    },
]

TRIPS = [
    {
        "title": "青岛周末两日",
        "destination": "青岛",
        "start_date": "2026-05-01",
        "end_date": "2026-05-02",
        "summary": "海边走路、喝原浆、吃蛤蜊，两天刚好。",
        "content_md": (
            "## Day 1\n\n栈桥到八大关一路走过去，五月的风刚刚好。\n\n"
            "## Day 2\n\n早市的蛤蜊和原浆啤酒，比景点值得。\n"
        ),
    },
]

MOMENTS = [
    "花园上线了后端，现在每个版块都是活的。🌱",
    "发现 SQLite 的 WAL 模式对个人站来说真是够用又省心。",
]

ABOUT_MD = (
    "**Cylunex**，业余开发者。喜欢自己动手把想法做成能用的东西：健康数据、自动化、自部署服务。"
    "这座花园跑在一台阿里云 ECS 上，由 nginx 浇水。"
)


def seed() -> None:
    init_db()
    conn = connect()
    now = now_iso()
    try:
        if conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0:
            for p in POSTS:
                conn.execute(
                    """INSERT INTO posts (slug, title, summary, content_md, content_html,
                                          tags, status, published_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'published', ?, ?, ?)""",
                    (
                        p["slug"], p["title"], p["summary"], p["content_md"],
                        render_markdown(p["content_md"]), tags_to_json(p["tags"]),
                        now, now, now,
                    ),
                )
            print(f"posts: 插入 {len(POSTS)} 条")

        if conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
            for p in PROJECTS:
                conn.execute(
                    """INSERT INTO projects (name, description, tags, link, repo, status,
                                             sort_order, created_at, updated_at)
                       VALUES (?, ?, ?, '', '', ?, ?, ?, ?)""",
                    (
                        p["name"], p["description"], tags_to_json(p["tags"]),
                        p["status"], p["sort_order"], now, now,
                    ),
                )
            print(f"projects: 插入 {len(PROJECTS)} 条")

        if conn.execute("SELECT COUNT(*) FROM food").fetchone()[0] == 0:
            for f in FOOD:
                conn.execute(
                    """INSERT INTO food (title, emoji, rating, location, review, photo,
                                         tags, eaten_on, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, '', ?, ?, ?, ?)""",
                    (
                        f["title"], f["emoji"], f["rating"], f["location"], f["review"],
                        tags_to_json(f["tags"]), f["eaten_on"], now, now,
                    ),
                )
            print(f"food: 插入 {len(FOOD)} 条")

        if conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 0:
            for t in TRIPS:
                conn.execute(
                    """INSERT INTO trips (title, destination, start_date, end_date, summary,
                                          content_md, content_html, photos, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)""",
                    (
                        t["title"], t["destination"], t["start_date"], t["end_date"],
                        t["summary"], t["content_md"], render_markdown(t["content_md"]),
                        now, now,
                    ),
                )
            print(f"trips: 插入 {len(TRIPS)} 条")

        if conn.execute("SELECT COUNT(*) FROM moments").fetchone()[0] == 0:
            for m in MOMENTS:
                conn.execute(
                    "INSERT INTO moments (content_md, content_html, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (m, render_markdown(m), now, now),
                )
            print(f"moments: 插入 {len(MOMENTS)} 条")

        if conn.execute("SELECT COUNT(*) FROM about").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO about (id, content_md, content_html, links, updated_at) VALUES (1, ?, ?, '[]', ?)",
                (ABOUT_MD, render_markdown(ABOUT_MD), now),
            )
            print("about: 已初始化")

        conn.commit()
        print("seed 完成")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
