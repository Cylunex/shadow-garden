---
name: shadow-garden-content
description: Maintain Shadow Garden content through its restricted API. Use when asked to draft, publish, list, or update Chinese blog posts, travel notes, food records, daily notes, scenery collections, or their images for the personal portal.
---

# Shadow Garden Content

Use the restricted content API. Never edit the database, deployment files, or production source code for a content request.

## Workflow

1. Identify the content type: blog, trip, food, or daily entry.
2. Read `/api/editor/context` to understand current drafts and recent work.
3. Extract facts from the user's message and attachments. Do not invent dates, locations, ratings, prices, people, events, or sensory details.
4. Ask only for missing facts that materially affect accuracy.
5. Write concise first-person Chinese unless the user requests another voice.
6. Apply the publishing rule below.
7. Call the bundled API client.
8. Read the saved record back and report its public URL or draft status.

Read `references/api.md` before the first mutation in a conversation or whenever updating an existing record.

## Publishing Rules

- Create blog posts as `draft` unless the user explicitly says to publish, post, or put them online.
- Trips, food records, and daily entries become public immediately. Show the proposed text and request confirmation unless the user explicitly asked to record or publish it on the portal.
- Treat an explicit request such as “记到网站”“发到门户”“发布这篇” as publication approval.
- Never delete content. Tell the user deletion requires the administrator.
- When updating, prefer `PATCH` with only the requested fields. Fetch the current record first when context is needed.

## API Client

Run:

```bash
python "$HERMES_HOME/skills/shadow-garden-content/scripts/garden_api.py" get /api/posts
python "$HERMES_HOME/skills/shadow-garden-content/scripts/garden_api.py" post /api/posts --json /tmp/post.json
python "$HERMES_HOME/skills/shadow-garden-content/scripts/garden_api.py" patch /api/posts/12 --json /tmp/post.json
python "$HERMES_HOME/skills/shadow-garden-content/scripts/garden_api.py" upload /tmp/photo.jpg
```

Write request JSON to a temporary file with mode `600`, then remove it after the request. Never print, inspect, or reveal `SHADOW_GARDEN_AGENT_TOKEN`.

## Content Guidelines

- Blog: use a clear title, short summary, 2–5 relevant tags, natural section headings, and a specific conclusion.
- Trip: organize chronologically when possible; distinguish observed facts from later reflections.
- Food: keep the review concrete and short; use a 1–5 rating only when the user supplied or approved it. Put the main image in `photo` and additional images in `photos`.
- Daily entry: use `note` for life notes and `scenery` for photos or observations of everyday scenery. Add concise collection names such as `晚霞` or `散步` when entries belong together; reuse existing names from `/api/editor/context` or the user's wording instead of inventing near-duplicates.
- Images: upload only user-provided images, then use the returned `/uploads/...` URL.

## Verification

- Blog URL: `/blog/post.html?slug=<slug>`; drafts have no public URL.
- Trip URL: `/travel/trip.html?id=<id>`.
- Food URL: `/food/`.
- Daily URL: `/moments/`; collection filter: `/moments/?collection=<name>`.
- After every mutation, verify the returned fields and state whether it is draft or public.
