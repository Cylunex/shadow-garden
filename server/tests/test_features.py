"""第二轮功能：浏览计数、翻页、搜索、说说、RSS/sitemap、导出。"""


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

    resp = client.post("/api/moments", json={"content_md": "**今天天气不错**"}, headers=admin_headers)
    assert resp.status_code == 201
    mid = resp.json()["id"]
    assert "<strong>" in resp.json()["content_html"]

    resp = client.put(f"/api/moments/{mid}", json={"content_md": "改一下"}, headers=admin_headers)
    assert "改一下" in resp.json()["content_md"]

    assert len(client.get("/api/moments").json()["items"]) == 1
    assert client.delete(f"/api/moments/{mid}", headers=admin_headers).status_code == 200
    assert client.get("/api/moments").json()["items"] == []


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


def test_geo_fields_roundtrip(client, admin_headers):
    # 坐标可选：不填为 null，填了原样返回，越界拒绝
    resp = client.post("/api/food", json={"title": "无坐标"}, headers=admin_headers)
    assert resp.json()["lat"] is None

    resp = client.post(
        "/api/food",
        json={"title": "有坐标", "lat": 36.067, "lng": 120.383},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["lat"] == 36.067

    assert client.post(
        "/api/food", json={"title": "越界", "lat": 91}, headers=admin_headers
    ).status_code == 422

    resp = client.post(
        "/api/trips",
        json={"title": "青岛", "lat": 36.067, "lng": 120.383},
        headers=admin_headers,
    )
    tid = resp.json()["id"]
    detail = client.get(f"/api/trips/{tid}").json()
    assert (detail["lat"], detail["lng"]) == (36.067, 120.383)

    # 清掉坐标
    client.put(f"/api/trips/{tid}", json={"title": "青岛"}, headers=admin_headers)
    assert client.get(f"/api/trips/{tid}").json()["lat"] is None


def test_summary_includes_moments(client, admin_headers):
    client.post("/api/moments", json={"content_md": "首页可见"}, headers=admin_headers)
    data = client.get("/api/summary").json()
    assert len(data["moments"]) == 1
