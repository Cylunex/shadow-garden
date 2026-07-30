# Shadow Garden Content API

Base URL and token come from `SHADOW_GARDEN_API_URL` and
`SHADOW_GARDEN_AGENT_TOKEN`. Send the token as `Authorization: Bearer ...`.

The content token permits `GET`, `POST`, and `PUT` on supported content paths.
It does not permit deletion, project management, about-page changes, or admin login.

## Blog

- List, including drafts: `GET /api/posts`
- Read: `GET /api/posts/{slug}`
- Create: `POST /api/posts`
- Update: `PUT /api/posts/{id}`

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

`status` is `draft` or `published`. An update is a full replacement; preserve
all unchanged fields from the existing record.

## Travel

- List: `GET /api/trips`
- Read: `GET /api/trips/{id}`
- Create: `POST /api/trips`
- Update: `PUT /api/trips/{id}`

```json
{
  "title": "标题",
  "destination": "目的地",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "summary": "摘要",
  "content_md": "Markdown 游记",
  "photos": ["/uploads/example.jpg"]
}
```

## Food

- List: `GET /api/food`
- Create: `POST /api/food`
- Update: `PUT /api/food/{id}`

```json
{
  "title": "名称",
  "emoji": "🍽️",
  "rating": 5,
  "location": "地点",
  "review": "评价",
  "photo": "/uploads/example.jpg",
  "tags": ["标签"],
  "eaten_on": "YYYY-MM-DD"
}
```

Rating must be 1–5. Do not guess it.

## Moments

- List: `GET /api/moments`
- Create: `POST /api/moments`
- Update: `PUT /api/moments/{id}`

```json
{
  "content_md": "短内容"
}
```

## Images

Upload a local user-provided image with:

```bash
python "$HERMES_HOME/skills/shadow-garden-content/scripts/garden_api.py" upload /path/to/photo.jpg
```

The result contains a relative URL in `url`. Use it in the content payload.
