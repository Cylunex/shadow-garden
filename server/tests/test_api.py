def test_legacy_password_login_is_removed(client):
    resp = client.post("/api/auth/login", json={"password": "nope"})
    assert resp.status_code == 405


def test_mutations_require_auth(client):
    assert client.post("/api/posts", json={"title": "x"}).status_code == 401
    assert client.post("/api/projects", json={"name": "x"}).status_code == 401
    assert client.post("/api/food", json={"title": "x"}).status_code == 401
    assert client.post("/api/trips", json={"title": "x"}).status_code == 401
    assert client.put("/api/about", json={"content_md": "x"}).status_code == 401


def test_content_agent_scope(client, agent_headers):
    created = client.post(
        "/api/posts",
        json={"title": "Agent 草稿", "content_md": "初稿"},
        headers=agent_headers,
    )
    assert created.status_code == 201
    post = created.json()
    assert post["status"] == "draft"

    visible = client.get(f"/api/posts/{post['slug']}", headers=agent_headers)
    assert visible.status_code == 200

    updated = client.put(
        f"/api/posts/{post['id']}",
        json={
            "title": "Agent 草稿",
            "slug": post["slug"],
            "content_md": "已修改",
            "status": "published",
        },
        headers=agent_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "published"

    assert client.delete(
        f"/api/posts/{post['id']}", headers=agent_headers
    ).status_code == 401
    assert client.post(
        "/api/projects", json={"name": "越权"}, headers=agent_headers
    ).status_code == 401
    assert client.put(
        "/api/about", json={"content_md": "越权"}, headers=agent_headers
    ).status_code == 401


def test_content_agent_context_and_partial_updates(client, agent_headers):
    created = client.post(
        "/api/posts",
        json={
            "title": "保留字段",
            "summary": "不能丢",
            "content_md": "旧正文",
            "tags": ["Agent"],
        },
        headers=agent_headers,
    ).json()

    patched = client.patch(
        f"/api/posts/{created['id']}",
        json={"content_md": "新正文"},
        headers=agent_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "保留字段"
    assert patched.json()["summary"] == "不能丢"
    assert patched.json()["tags"] == ["Agent"]
    assert patched.json()["content_md"] == "新正文"

    daily = client.post(
        "/api/moments",
        json={
            "title": "晚霞",
            "kind": "scenery",
            "photos": ["/uploads/sunset.jpg"],
            "collections": ["晚霞"],
        },
        headers=agent_headers,
    )
    assert daily.status_code == 201

    context = client.get("/api/editor/context", headers=agent_headers)
    assert context.status_code == 200
    assert context.json()["agent_configured"] is True
    assert context.json()["counts"]["drafts"] == 1
    assert context.json()["daily_collections"] == [{"name": "晚霞", "count": 1}]
    assert context.json()["recent_daily"][0]["kind"] == "scenery"
    assert context.json()["capabilities"]["delete"] == []
    assert client.get("/api/editor/context").status_code == 401


def test_content_agent_partial_updates_preserve_other_content(client, agent_headers):
    food = client.post(
        "/api/food",
        json={"title": "面馆", "location": "楼下", "rating": 4},
        headers=agent_headers,
    ).json()
    food_updated = client.patch(
        f"/api/food/{food['id']}",
        json={"rating": 5},
        headers=agent_headers,
    ).json()
    assert food_updated["title"] == "面馆"
    assert food_updated["location"] == "楼下"

    trip = client.post(
        "/api/trips",
        json={"title": "周末", "destination": "青岛", "content_md": "海边"},
        headers=agent_headers,
    ).json()
    trip_updated = client.patch(
        f"/api/trips/{trip['id']}",
        json={"summary": "两天刚好"},
        headers=agent_headers,
    ).json()
    assert trip_updated["destination"] == "青岛"
    assert trip_updated["content_md"] == "海边"

    moment = client.post(
        "/api/moments",
        json={
            "title": "散步时的云",
            "kind": "scenery",
            "content_md": "旧内容",
            "photos": ["/uploads/cloud.jpg"],
            "collections": ["散步", "天空"],
        },
        headers=agent_headers,
    ).json()
    moment_updated = client.patch(
        f"/api/moments/{moment['id']}",
        json={"content_md": "新内容"},
        headers=agent_headers,
    ).json()
    assert moment_updated["content_md"] == "新内容"
    assert moment_updated["title"] == "散步时的云"
    assert moment_updated["kind"] == "scenery"
    assert moment_updated["photos"] == ["/uploads/cloud.jpg"]
    assert moment_updated["collections"] == ["散步", "天空"]


def test_post_lifecycle(client, admin_headers):
    # 建草稿
    resp = client.post(
        "/api/posts",
        json={"title": "测试文章", "content_md": "# 你好\n\n**加粗**", "tags": ["测试"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    post = resp.json()
    assert post["status"] == "draft"
    assert "<strong>加粗</strong>" in post["content_html"]

    # 公开列表看不到草稿，管理端能看到
    assert client.get("/api/posts").json()["items"] == []
    assert len(client.get("/api/posts", headers=admin_headers).json()["items"]) == 1
    assert client.get(f"/api/posts/{post['slug']}").status_code == 404

    # 发布
    resp = client.put(
        f"/api/posts/{post['id']}",
        json={"title": "测试文章", "slug": post["slug"], "content_md": "改过了",
              "tags": ["测试"], "status": "published"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["published_at"]

    public = client.get(f"/api/posts/{post['slug']}")
    assert public.status_code == 200
    assert "改过了" in public.json()["content_html"]

    # 按标签筛选
    assert len(client.get("/api/posts", params={"tag": "测试"}).json()["items"]) == 1
    assert client.get("/api/posts", params={"tag": "没有"}).json()["items"] == []

    # 删除
    assert client.delete(f"/api/posts/{post['id']}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/posts/{post['slug']}").status_code == 404


def test_post_slug_dedup(client, admin_headers):
    a = client.post("/api/posts", json={"title": "x", "slug": "same"}, headers=admin_headers)
    b = client.post("/api/posts", json={"title": "y", "slug": "same"}, headers=admin_headers)
    assert a.json()["slug"] == "same"
    assert b.json()["slug"] == "same-2"


def test_project_crud(client, admin_headers):
    resp = client.post(
        "/api/projects",
        json={"name": "试验项目", "tags": ["Python"], "status": "planned", "sort_order": 5},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]
    assert resp.json()["status_label"] == "计划中"

    resp = client.put(
        f"/api/projects/{pid}",
        json={"name": "试验项目", "status": "done"},
        headers=admin_headers,
    )
    assert resp.json()["status"] == "done"

    assert len(client.get("/api/projects").json()["items"]) == 1
    assert client.delete(f"/api/projects/{pid}", headers=admin_headers).status_code == 200


def test_food_crud_and_rating_bounds(client, admin_headers):
    bad = client.post("/api/food", json={"title": "x", "rating": 6}, headers=admin_headers)
    assert bad.status_code == 422

    resp = client.post(
        "/api/food",
        json={
            "title": "牛肉面",
            "rating": 5,
            "location": "楼下",
            "eaten_on": "2026-07-10",
            "photo": "/uploads/cover.jpg",
            "photos": ["/uploads/a.jpg", "/uploads/b.jpg"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    food = client.get("/api/food").json()["items"][0]
    assert food["title"] == "牛肉面"
    assert food["photo"] == "/uploads/cover.jpg"
    assert food["photos"] == ["/uploads/a.jpg", "/uploads/b.jpg"]

    updated = client.patch(
        f"/api/food/{food['id']}",
        json={"photos": ["/uploads/c.jpg"]},
        headers=admin_headers,
    ).json()
    assert updated["photo"] == "/uploads/cover.jpg"
    assert updated["photos"] == ["/uploads/c.jpg"]


def test_trip_crud(client, admin_headers):
    resp = client.post(
        "/api/trips",
        json={"title": "青岛", "destination": "青岛", "start_date": "2026-05-01",
              "content_md": "## Day 1\n\n海边"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    tid = resp.json()["id"]

    detail = client.get(f"/api/trips/{tid}")
    assert detail.status_code == 200
    assert "<h2>Day 1</h2>" in detail.json()["content_html"]


def test_about_roundtrip(client, admin_headers):
    # 未初始化时返回默认内容
    assert client.get("/api/about").status_code == 200

    resp = client.put(
        "/api/about",
        json={"content_md": "**我**", "links": [{"label": "GitHub", "url": "https://github.com/x"}]},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = client.get("/api/about").json()
    assert "<strong>我</strong>" in data["content_html"]
    assert data["links"][0]["label"] == "GitHub"


def test_upload_validation_and_success(client, admin_headers):
    bad = client.post(
        "/api/uploads",
        files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
        headers=admin_headers,
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/uploads",
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n123", "image/png")},
        headers=admin_headers,
    )
    assert ok.status_code == 201
    url = ok.json()["url"]
    assert url.startswith("/uploads/") and url.endswith(".png")
    assert client.get(url).status_code == 200


def test_summary_shape(client, admin_headers):
    client.post("/api/posts", json={"title": "p", "status": "published"}, headers=admin_headers)
    client.post("/api/projects", json={"name": "j"}, headers=admin_headers)
    data = client.get("/api/summary").json()
    assert {"posts", "projects", "food", "trips"} <= set(data)
    assert len(data["posts"]) == 1


def test_logout_invalidates_browser_session(client, admin_headers):
    assert client.get("/api/auth/me", headers=admin_headers).json()["admin"] is True
    client.post("/auth/logout", headers=admin_headers)
    assert client.get("/api/auth/me", headers=admin_headers).json()["admin"] is False
    assert client.post("/api/posts", json={"title": "x"}, headers=admin_headers).status_code == 401


def test_browser_writes_require_same_origin(client, admin_headers):
    headers = {"Cookie": admin_headers["Cookie"]}
    assert client.post("/api/posts", json={"title": "x"}, headers=headers).status_code == 403
