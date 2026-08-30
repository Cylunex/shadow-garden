"""种子数据：python -m app.seed（在 server/ 目录）。只在对应表为空时插入。"""
from .db import connect, now_iso, tags_to_json
from .migrations import upgrade
from .rendering import render_markdown

POSTS = [
    {
        "slug": "hello-world",
        "title": "Hello World：欢迎来到这座花园",
        "summary": "这里记录持续生长的文章、项目、旅途和日常片段。",
        "content_md": (
            "这座花园用来保存仍在生长的内容：\n\n"
            "- 写下正在形成的想法\n"
            "- 整理项目和长期主题\n"
            "- 留住旅行、美食与日常片段\n\n"
            "内容不必一次完成，愿意持续回来浇水就好。\n"
        ),
        "tags": ["花园", "碎碎念"],
    },
    {
        "slug": "why-digital-garden",
        "title": "为什么保留一座数字花园",
        "summary": "比起一次性发布，更看重内容在时间里的生长和连接。",
        "content_md": (
            "传统文章像完成后的展品，数字花园更像工作台。\n\n"
            "旧笔记可以被修订，新项目可以和过去的想法重新建立连接。\n"
            "重要的不是更新频率，而是让值得保留的内容始终可找、可读、可继续。\n"
        ),
        "tags": ["写作", "数字花园"],
    },
]

PROJECTS = [
    {
        "name": "Shadow Garden",
        "description": "持续生长的个人数字花园：集中展示项目、博客、日常风景、美食与旅行记录，自部署、数据自持。",
        "tags": ["FastAPI", "PostgreSQL", "Redis"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-garden",
        "status": "active",
        "sort_order": 100,
    },
    {
        "name": "Shadow Platform",
        "description": "Shadow 系列项目的共享基础设施，统一提供身份认证、资产存储、应用目录、Agent 控制面、通知与遥测能力。",
        "tags": ["Python", "OIDC", "Asset", "Agent"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-platform",
        "status": "active",
        "sort_order": 90,
    },
    {
        "name": "Shadow Health",
        "description": "个人健康数据中枢：统一记录饮食、训练、睡眠、体测与多设备数据，支持离线使用、AI 分析和多 Agent 接入。",
        "tags": ["FastAPI", "PostgreSQL", "PWA", "MCP"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-health",
        "status": "active",
        "sort_order": 80,
    },
    {
        "name": "Shadow Travel",
        "description": "以地图为中心的主题地点收藏工具，可规划旅行与美食地图、记录到访和照片，并和同行人协作维护。",
        "tags": ["FastAPI", "PostgreSQL", "地图", "协作"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-travel",
        "status": "active",
        "sort_order": 70,
    },
    {
        "name": "Shadow Ledger",
        "description": "以消费为中心的个人收支记录与规划系统，保留金额事实、消费记忆和未来计划，并提供完整审计链路。",
        "tags": ["FastAPI", "PostgreSQL", "OIDC", "财务"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-ledger",
        "status": "active",
        "sort_order": 60,
    },
    {
        "name": "Shadow Archive",
        "description": "个人互联网内容档案与数字记忆层，统一收藏文章、图片、视频和零散片段，让保存的内容可搜索、可关联、可回顾。",
        "tags": ["React", "Python", "PostgreSQL", "AI"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-archive",
        "status": "active",
        "sort_order": 50,
    },
    {
        "name": "Shadow Foliant",
        "description": "面向 A 股个人投研的 Agent-first 系统，把行情、选股、持仓、风险、回测与真实结果反馈串成闭环。",
        "tags": ["Python", "FastAPI", "MCP", "量化投研"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-foliant",
        "status": "active",
        "sort_order": 40,
    },
    {
        "name": "Shadow App",
        "description": "Shadow 系列服务的独立 Android 壳，通过统一身份和应用目录，在安全 WebView 容器中访问各个自部署应用。",
        "tags": ["Android", "Kotlin", "WebView", "OIDC"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-app",
        "status": "active",
        "sort_order": 30,
    },
    {
        "name": "Shadow Verse",
        "description": "生成并连接无数世界的 AIGC 多元宇宙引擎，可用于叙事创作、角色扮演、世界模拟与跨世界体验。",
        "tags": ["Python", "AIGC", "MCP", "创作引擎"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-verse",
        "status": "active",
        "sort_order": 20,
    },
    {
        "name": "Shadow Wingman",
        "description": "可移植的中文 AI 恋爱与社交沟通陪练，通过自然角色扮演练习聊天、邀约、约会与关系沟通。",
        "tags": ["AI", "角色扮演", "沟通陪练", "Skill"],
        "link": "",
        "repo": "https://github.com/Cylunex/shadow-wingman",
        "status": "active",
        "sort_order": 10,
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
    "这座花园用于整理项目、文章和生活片段。"
)


def _count(conn, table: str) -> int:
    # 两个后端的行对象都按列名取值（psycopg 的 dict 行没有位置下标）
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def seed() -> None:
    upgrade()
    conn = connect()
    now = now_iso()
    try:
        if _count(conn, "posts") == 0:
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

        if _count(conn, "projects") == 0:
            for p in PROJECTS:
                conn.execute(
                    """INSERT INTO projects (name, description, tags, link, repo, status,
                                             sort_order, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        p["name"], p["description"], tags_to_json(p["tags"]),
                        p["link"], p["repo"], p["status"], p["sort_order"], now, now,
                    ),
                )
            print(f"projects: 插入 {len(PROJECTS)} 条")

        if _count(conn, "food") == 0:
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

        if _count(conn, "trips") == 0:
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

        if _count(conn, "moments") == 0:
            for m in MOMENTS:
                conn.execute(
                    "INSERT INTO moments (content_md, content_html, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (m, render_markdown(m), now, now),
                )
            print(f"moments: 插入 {len(MOMENTS)} 条")

        if _count(conn, "about") == 0:
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
