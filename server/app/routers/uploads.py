import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from ..auth import require_admin
from ..config import settings

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("", dependencies=[Depends(require_admin)], status_code=201)
async def upload_image(file: UploadFile):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"只支持图片：{', '.join(sorted(ALLOWED_EXT))}")

    limit = settings.max_upload_mb * 1024 * 1024
    content = await file.read()
    if len(content) > limit:
        raise HTTPException(413, f"文件超过 {settings.max_upload_mb}MB 限制")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    name = f"{stamp}-{secrets.token_hex(6)}{ext}"
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.uploads_dir / name).write_bytes(content)
    return {"url": f"/uploads/{name}", "size": len(content)}
