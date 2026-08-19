import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from ..assets import GardenAssetError, upload_public_image
from ..auth import require_content_editor
from ..config import settings
from ..db import get_db, now_iso

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("", dependencies=[Depends(require_content_editor)], status_code=201)
async def upload_image(file: UploadFile, conn=Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"只支持图片：{', '.join(sorted(ALLOWED_EXT))}")

    limit = settings.max_upload_mb * 1024 * 1024
    content = await file.read()
    if len(content) > limit:
        raise HTTPException(413, f"文件超过 {settings.max_upload_mb}MB 限制")

    if settings.asset_mode == "platform":
        record_id = str(uuid.uuid4())
        try:
            uploaded = upload_public_image(
                record_id=record_id,
                original_filename=Path(file.filename or "image").name,
                content_type=(file.content_type or "application/octet-stream").lower(),
                content=content,
            )
        except GardenAssetError as exc:
            raise HTTPException(502, str(exc)) from exc
        conn.execute(
            """INSERT INTO asset_files
               (id, asset_id, version_id, reference_id, url, original_filename,
                content_type, size_bytes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id,
                uploaded.asset_id,
                uploaded.version_id,
                uploaded.reference_id,
                uploaded.url,
                Path(file.filename or "image").name,
                (file.content_type or "application/octet-stream").lower(),
                len(content),
                now_iso(),
            ),
        )
        return {
            "url": uploaded.url,
            "size": len(content),
            "asset_id": uploaded.asset_id,
            "version_id": uploaded.version_id,
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    name = f"{stamp}-{secrets.token_hex(6)}{ext}"
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.uploads_dir / name).write_bytes(content)
    return {"url": f"/uploads/{name}", "size": len(content)}
