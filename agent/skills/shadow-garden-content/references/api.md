# Shadow Garden Content API

Base URL and token come from `SHADOW_GARDEN_API_URL` and
`SHADOW_GARDEN_AGENT_TOKEN`. Send the token as `Authorization: Bearer ...`.

The content token permits `GET`, `POST`, `PUT`, and `PATCH` on supported content paths.
It does not permit deletion, project management, about-page changes, or admin login.

## Context

- Current counts, drafts, recent posts, and permissions: `GET /api/editor/context`

Use this before starting a content task so existing drafts are not duplicated.

## Blog

- List, including drafts: `GET /api/posts`
- Read: `GET /api/posts/{slug}`
- Create: `POST /api/posts`
- Update: `PUT /api/posts/{id}`
- Partial update (preferred): `PATCH /api/posts/{id}`

```json
{
  "title": "标题",
  "slug": "",
  "summary": "摘要",
  "content_md": "Markdown 正文",
  "tags": ["标签"],
  "status": "draft"
}
```

`status` is `draft` or `published`. `PUT` is a full replacement. Prefer `PATCH`
with only the fields requested by the user.

## Travel

- List: `GET /api/trips`
- Read: `GET /api/trips/{id}`
- Create: `POST /api/trips`
- Update: `PUT /api/trips/{id}`
- Partial update (preferred): `PATCH /api/trips/{id}`

```json
{
  "title": "标题",
  "destination": "目的地",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "summary": "摘要",
  "content_md": "Markdown 游记",
  "photos": ["https://media.example.com/v1/asset-content/example-version?operation=inline"]
}
```

## Food

- List: `GET /api/food`
- Create: `POST /api/food`
- Update: `PUT /api/food/{id}`
- Partial update (preferred): `PATCH /api/food/{id}`

```json
{
  "title": "名称",
  "emoji": "🍽️",
  "rating": 5,
  "location": "地点",
  "review": "评价",
  "photo": "https://media.example.com/v1/asset-content/cover-version?operation=inline",
  "photos": ["https://media.example.com/v1/asset-content/detail-version?operation=inline"],
  "tags": ["标签"],
  "eaten_on": "YYYY-MM-DD"
}
```

Rating must be 1–5. Do not guess it.
`photo` is the optional cover image. `photos` is the gallery; when the cover is
empty, the site uses the first gallery image as the cover.

## Daily Notes and Scenery

- List: `GET /api/moments`
- Create: `POST /api/moments`
- Update: `PUT /api/moments/{id}`
- Partial update (preferred): `PATCH /api/moments/{id}`

```json
{
  "title": "今天的晚霞",
  "kind": "scenery",
  "content_md": "下班路上遇到的一片橘色。",
  "photos": ["https://media.example.com/v1/asset-content/sunset-version?operation=inline"],
  "collections": ["晚霞"]
}
```

`kind` is `note` for daily records or `scenery` for everyday scenery. At least
one of `title`, `content_md`, or `photos` is required. Reuse collection names so
the site can automatically group entries into albums such as `晚霞合集`.

## Images

Upload a local user-provided image with:

```bash
python "$HERMES_HOME/skills/shadow-garden-content/scripts/garden_api.py" upload /path/to/photo.jpg
```

The upload endpoint now stores new originals in Shadow Asset v1 and returns its public
content URL. Historical `/uploads/...` values remain readable but should not be created by
new clients.

The result contains an absolute Asset content URL in `url`. Use it unchanged in the content payload.
