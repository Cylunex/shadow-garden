---
name: shadow-garden-content
description: Read Shadow Garden status and create reviewable Chinese article drafts through its restricted Agent API.
---

# Shadow Garden Content

Use the restricted content API. Never edit the database, deployment files, or production source code for a content request.

## Workflow

1. Read `garden.summary.get` when current Garden context matters.
2. Identify the requested article's title, summary, body, tags, and optional slug.
3. Extract facts from the user's message and attachments. Do not invent dates, locations, ratings, prices, people, events, or sensory details.
4. Ask only for missing facts that materially affect accuracy.
5. Write concise first-person Chinese unless the user requests another voice.
6. Call `garden.posts.draft` once with an idempotency key.
7. Report the resulting review id and draft status.

## Publishing Rules

- Always create an article as a private draft, including when the user says “发布”.
- Public publication is an L3 Host action. It requires the user to confirm the exact draft in Nexus and cannot be performed by this Skill.
- Never delete content or bypass the review endpoint through legacy content APIs.

## Content Guidelines

- Blog: use a clear title, short summary, 2–5 relevant tags, natural section headings, and a specific conclusion.
- Images: reference only user-provided Shadow Asset URLs and keep them unchanged.

## Verification

- Drafts have no public URL. After creation, verify the returned `review_id`, fields and `state=pending`.
