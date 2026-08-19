"""Shadow Asset v1 integration for Garden-owned public images."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shadow_sdk.assets import AssetClient, AssetClientError

from .config import settings


class GardenAssetError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GardenAssetUpload:
    asset_id: str
    version_id: str
    reference_id: str
    url: str


@dataclass(frozen=True, slots=True)
class GardenAssetUploadSession:
    record_id: str
    upload_session_id: str
    expires_at: str
    target: dict[str, Any]
    alternate_targets: tuple[dict[str, Any], ...]


def _service_token() -> str:
    path = Path(settings.asset_service_token_file).expanduser()
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise GardenAssetError("Asset 服务凭据不可用") from exc
    if not token:
        raise GardenAssetError("Asset 服务凭据为空")
    return token


def create_public_image_upload(
    *,
    record_id: str,
    original_filename: str,
    content_type: str,
    size_bytes: int,
) -> GardenAssetUploadSession:
    """Create a short-lived upload session without exposing the Garden service credential."""

    try:
        with AssetClient(settings.asset_base_url, _service_token()) as client:
            session = client.create_upload_session(
                owner_id=settings.asset_owner_id,
                ownership_mode="app_managed",
                access_mode="public",
                sensitivity="normal",
                original_filename=original_filename,
                content_type=content_type,
                size_bytes=size_bytes,
                display_name=original_filename,
                idempotency_key=f"garden:asset:{record_id}:upload",
            )
    except (AssetClientError, KeyError, TypeError, ValueError) as exc:
        raise GardenAssetError("Asset 服务创建上传会话失败") from exc

    target = session.get("target")
    alternates = session.get("alternate_targets") or []
    if not isinstance(target, dict) or not isinstance(alternates, list):
        raise GardenAssetError("Asset 服务没有返回有效上传目标")
    return GardenAssetUploadSession(
        record_id=record_id,
        upload_session_id=str(session["upload_session_id"]),
        expires_at=str(session["expires_at"]),
        target=target,
        alternate_targets=tuple(item for item in alternates if isinstance(item, dict)),
    )


def complete_public_image_upload(
    *, record_id: str, upload_session_id: str
) -> GardenAssetUpload:
    """Finalize uploaded bytes and bind the resulting version to Garden."""

    try:
        with AssetClient(settings.asset_base_url, _service_token()) as client:
            asset = client.complete_upload(upload_session_id)
            version_id = str(asset["current_version_id"])
            reference = client.create_reference(
                asset_id=str(asset["id"]),
                resource_uri=f"shadow://garden/assets/{record_id}",
                usage_role="original",
                reference_key=f"garden:asset:{record_id}",
                binding_mode="pinned",
                pinned_version_id=version_id,
            )
            grant = client.grant_access(version_id, operation="inline")
    except (AssetClientError, KeyError, TypeError, ValueError) as exc:
        raise GardenAssetError("Asset 服务完成上传失败") from exc

    url = grant.get("url")
    if not isinstance(url, str) or not url:
        raise GardenAssetError("Asset 服务没有返回有效访问地址")
    return GardenAssetUpload(
        asset_id=str(asset["id"]),
        version_id=version_id,
        reference_id=str(reference["id"]),
        url=url,
    )


def upload_public_image(
    *,
    record_id: str,
    original_filename: str,
    content_type: str,
    content: bytes,
) -> GardenAssetUpload:
    """Compatibility path for Agents and older clients that send bytes through Garden."""

    session = create_public_image_upload(
        record_id=record_id,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=len(content),
    )
    try:
        with AssetClient(settings.asset_base_url, _service_token()) as client:
            client.upload_bytes(session.target, content)
    except (AssetClientError, KeyError, TypeError, ValueError) as exc:
        raise GardenAssetError("Asset 服务上传失败") from exc
    return complete_public_image_upload(
        record_id=record_id,
        upload_session_id=session.upload_session_id,
    )
