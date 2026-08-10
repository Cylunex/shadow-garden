"""第二轮及以后功能：浏览计数、翻页、搜索、说说、RSS/sitemap、导出、浇水、统计、漫步。"""
import os


def _publish(client, headers, title, slug, content="正文"):
    resp = client.post(
        "/api/posts",
        json={"title": title, "slug": slug, "content_md": content, "status": "published"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def test_views_increment_public_only(client, admin_headers):
    _publish(client, admin_headers, "计数", "views-test")

    # 管理端预览不计数
    client.get("/api/posts/views-test", headers=admin_headers)
    assert client.get("/api/posts/views-test", headers=admin_headers).json()["views"] == 0

    # 公开访问计数
    client.get("/api/posts/views-test")
    assert client.get("/api/posts/views-test").json()["views"] == 2


def test_prev_next_navigation(client, admin_headers):
    a = _publish(client, admin_headers, "第一篇", "nav-a")
    b = _publish(client, admin_headers, "第二篇", "nav-b")
    c = _publish(client, admin_headers, "第三篇", "nav-c")

    mid = client.get("/api/posts/nav-b").json()
    assert mid["prev"]["slug"] == "nav-a"
    assert mid["next"]["slug"] == "nav-c"
    assert client.get("/api/posts/nav-a").json()["prev"] is None
    assert client.get("/api/posts/nav-c").json()["next"] is None


def test_reading_stats(client, admin_headers):
    _publish(client, admin_headers, "统计", "stats", content="你好世界 hello world " * 100)
    data = client.get("/api/posts/stats").json()
    assert data["word_count"] == 600  # 4 汉字 + 2 英文词，×100
    assert data["reading_minutes"] >= 1


def test_search(client, admin_headers):
    _publish(client, admin_headers, "青岛游记攻略", "search-hit", content="海边的原浆啤酒")
    client.post("/api/posts", json={"title": "草稿里的青岛", "content_md": "青岛"}, headers=admin_headers)

    # 按标题命中
    assert len(client.get("/api/search", params={"q": "青岛"}).json()["posts"]) == 1
    # 按正文命中
    assert len(client.get("/api/search", params={"q": "原浆"}).json()["posts"]) == 1
    # 通配符不注入
    assert client.get("/api/search", params={"q": "%"}).json()["posts"] == []
    # 空查询
    assert client.get("/api/search", params={"q": " "}).json() == {"posts": [], "trips": []}


def test_moments_crud(client, admin_headers):
    assert client.post("/api/moments", json={"content_md": "x"}).status_code == 401
    assert client.post("/api/moments", json={}, headers=admin_headers).status_code == 422

    resp = client.post("/api/moments", json={"content_md": "**今天天气不错**"}, headers=admin_headers)
    assert resp.status_code == 201
    mid = resp.json()["id"]
    assert "<strong>" in resp.json()["content_html"]

    resp = client.put(f"/api/moments/{mid}", json={"content_md": "改一下"}, headers=admin_headers)
    assert "改一下" in resp.json()["content_md"]

    scenery = client.post(
        "/api/moments",
        json={
            "title": "窗外的晚霞",
            "kind": "scenery",
            "photos": ["/uploads/a.jpg", "/uploads/b.jpg"],
            "collections": ["晚霞"],
        },
        headers=admin_headers,
    )
    assert scenery.status_code == 201
    assert scenery.json()["content_md"] == ""
    assert scenery.json()["photos"] == ["/uploads/a.jpg", "/uploads/b.jpg"]
    assert scenery.json()["collections"] == ["晚霞"]

    assert len(client.get("/api/moments").json()["items"]) == 2
    assert client.delete(f"/api/moments/{mid}", headers=admin_headers).status_code == 200
    assert len(client.get("/api/moments").json()["items"]) == 1


def test_feed_and_sitemap(client, admin_headers):
    _publish(client, admin_headers, "RSS 测试文章", "rss-post")
    feed = client.get("/feed.xml")
    assert feed.status_code == 200
    assert "application/rss+xml" in feed.headers["content-type"]
    assert "RSS 测试文章" in feed.text and "rss-post" in feed.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "rss-post" in sitemap.text and "/moments/" in sitemap.text


def test_export_requires_admin_and_is_complete(client, admin_headers):
    assert client.get("/api/export").status_code == 401

    client.post("/api/moments", json={"content_md": "备份我"}, headers=admin_headers)
    data = client.get("/api/export", headers=admin_headers).json()
    assert {"posts", "projects", "food", "trips", "moments", "about"} <= set(data)
    assert data["moments"][0]["content_md"] == "备份我"


def test_code_highlight_rendering(client, admin_headers):
    _publish(client, admin_headers, "高亮", "hl",
             content="```python\nprint('hi')\n```")
    html = client.get("/api/posts/hl").json()["content_html"]
    assert 'class="highlight"' in html


def test_water(client, admin_headers):
    _publish(client, admin_headers, "浇水测试", "water-me")

    # 草稿不能浇
    client.post("/api/posts", json={"title": "草稿", "slug": "draft-w"}, headers=admin_headers)
    assert client.post("/api/posts/draft-w/water").status_code == 404

    r1 = client.post("/api/posts/water-me/water").json()
    assert r1 == {"waters": 1, "watered": True}

    r2 = client.post("/api/posts/water-me/water").json()
    if os.environ.get("REDIS_TEST_URL"):
        # Redis 防刷：同 IP 当天第二次不计数
        assert r2 == {"waters": 1, "watered": False}
    else:
        assert r2["waters"] == 2

    assert client.get("/api/posts/water-me").json()["waters"] == r2["waters"]


def test_stats(client, admin_headers):
    _publish(client, admin_headers, "统计文章", "stats-post", content="你好世界 " * 50)
    client.post("/api/moments", json={"content_md": "统计说说"}, headers=admin_headers)
    client.post("/api/food", json={"title": "统计菜", "rating": 4}, headers=admin_headers)

    data = client.get("/api/stats").json()
    assert data["counts"]["posts"] == 1
    assert data["counts"]["moments"] == 1
    assert data["counts"]["food"] == 1
    assert data["words"] >= 200
    assert data["avg_food_rating"] == 4.0
    assert data["garden_age_days"] >= 1
    assert sum(d["count"] for d in data["heatmap"]) >= 3
    assert any(t["tag"] for t in data["top_tags"]) or data["top_tags"] == []


def test_random_walk(client, admin_headers):
    # 空花园兜底回首页
    resp = client.get("/api/random", follow_redirects=False)
    assert resp.status_code == 302 and resp.headers["location"] == "/"

    _publish(client, admin_headers, "漫步", "walk-post")
    resp = client.get("/api/random", follow_redirects=False)
    assert resp.headers["location"] == "/blog/post.html?slug=walk-post"


def test_summary_includes_moments(client, admin_headers):
    client.post("/api/moments", json={"content_md": "首页可见"}, headers=admin_headers)
    data = client.get("/api/summary").json()
    assert len(data["moments"]) == 1
