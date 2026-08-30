import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from ..assets import (
    GardenAssetError,
    GardenAssetUpload,
    complete_public_image_upload,
    create_public_image_upload,
    upload_public_image,
)
from ..auth import content_owner_id, require_content_editor
from ..config import settings
from ..db import get_db, now_iso

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class UploadInit(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)


class UploadComplete(BaseModel):
    upload_id: str = Field(min_length=36, max_length=36)


def _validated_metadata(filename: str, content_type: str, size_bytes: int) -> tuple[str, str]:
    clean_name = Path(filename).name
    extension = Path(clean_name).suffix.lower()
    if extension not in ALLOWED_EXT:
        raise HTTPException(400, f"只支持图片：{', '.join(sorted(ALLOWED_EXT))}")
    clean_type = content_type.split(";", 1)[0].strip().lower()
    if clean_type not in ALLOWED_MIME:
        raise HTTPException(400, "图片类型不受支持")
    if size_bytes > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"文件超过 {settings.max_upload_mb}MB 限制")
    return clean_name, clean_type


def _record_asset(
    conn,
    *,
    record_id: str,
    uploaded: GardenAssetUpload,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    owner_id: str,
) -> None:
    conn.execute(
        """INSERT INTO asset_files
           (id, owner_id, asset_id, version_id, reference_id, url, original_filename,
            content_type, size_bytes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record_id, owner_id,
            uploaded.asset_id,
            uploaded.version_id,
            uploaded.reference_id,
            uploaded.url,
            original_filename,
            content_type,
            size_bytes,
            now_iso(),
        ),
    )


def _upload_result(uploaded: GardenAssetUpload, size_bytes: int) -> dict[str, object]:
    return {
        "url": uploaded.url,
        "size": size_bytes,
        "asset_id": uploaded.asset_id,
        "version_id": uploaded.version_id,
    }


@router.post("/init", dependencies=[Depends(require_content_editor)], status_code=201)
def initialize_direct_upload(body: UploadInit, response: Response, owner_id: str = Depends(content_owner_id), conn=Depends(get_db)):
    if settings.asset_mode != "platform":
        raise HTTPException(409, "当前存储模式不支持直传")
    filename, content_type = _validated_metadata(
        body.filename, body.content_type, body.size_bytes
    )
    record_id = str(uuid.uuid4())
    try:
        session = create_public_image_upload(
            record_id=record_id,
            original_filename=filename,
            content_type=content_type,
            size_bytes=body.size_bytes,
        )
    except GardenAssetError as exc:
        raise HTTPException(502, str(exc)) from exc
    conn.execute(
        "DELETE FROM asset_uploads_pending WHERE status = 'pending' AND expires_at <= ?",
        (now_iso(),),
    )
    conn.execute(
        """INSERT INTO asset_uploads_pending
           (id, owner_id, upload_session_id, original_filename, content_type, size_bytes,
            status, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (
            record_id, owner_id,
            session.upload_session_id,
            filename,
            content_type,
            body.size_bytes,
            session.expires_at,
            now_iso(),
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "upload_id": record_id,
        "expires_at": session.expires_at,
        "targets": [*session.alternate_targets, session.target],
    }


@router.post("/complete", dependencies=[Depends(require_content_editor)])
def complete_direct_upload(body: UploadComplete, response: Response, owner_id: str = Depends(content_owner_id), conn=Depends(get_db)):
    row = conn.execute(
        "SELECT * FROM asset_uploads_pending WHERE id=? AND owner_id=?", (body.upload_id, owner_id)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "上传会话不存在")
    if row["status"] == "completed":
        response.headers["Cache-Control"] = "no-store"
        return {
            "url": row["url"],
            "size": row["size_bytes"],
            "asset_id": row["asset_id"],
            "version_id": row["version_id"],
        }
    if row["status"] != "pending":
        raise HTTPException(409, "上传会话状态无效")
    try:
        uploaded = complete_public_image_upload(
            record_id=row["id"],
            upload_session_id=row["upload_session_id"],
        )
    except GardenAssetError as exc:
        raise HTTPException(502, str(exc)) from exc
    _record_asset(
        conn,
        record_id=row["id"],
        uploaded=uploaded,
        original_filename=row["original_filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        owner_id=owner_id,
    )
    completed_at = now_iso()
    conn.execute(
        """UPDATE asset_uploads_pending
           SET status = 'completed', asset_id = ?, version_id = ?, reference_id = ?,
               url = ?, completed_at = ? WHERE id = ?""",
        (
            uploaded.asset_id,
            uploaded.version_id,
            uploaded.reference_id,
            uploaded.url,
            completed_at,
            row["id"],
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return _upload_result(uploaded, row["size_bytes"])


@router.post("", dependencies=[Depends(require_content_editor)], status_code=201)
async def upload_image(file: UploadFile, owner_id: str = Depends(content_owner_id), conn=Depends(get_db)):
    content = await file.read()
    filename, content_type = _validated_metadata(
        file.filename or "", file.content_type or "application/octet-stream", len(content)
    )
    ext = Path(filename).suffix.lower()

    if settings.asset_mode == "platform":
        record_id = str(uuid.uuid4())
        try:
            uploaded = upload_public_image(
                record_id=record_id,
                original_filename=filename,
                content_type=content_type,
                content=content,
            )
        except GardenAssetError as exc:
            raise HTTPException(502, str(exc)) from exc
        _record_asset(
            conn,
            record_id=record_id,
            uploaded=uploaded,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            owner_id=owner_id,
        )
        return _upload_result(uploaded, len(content))

    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    }
    if not signatures.get(content_type, False):
        raise HTTPException(400, "图片内容与声明类型不匹配")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    name = f"{stamp}-{secrets.token_hex(6)}{ext}"
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.uploads_dir / name).write_bytes(content)
    return {"url": f"/uploads/{name}", "size": len(content)}
