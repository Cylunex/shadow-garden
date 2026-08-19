"""Shadow Asset v1 integration for Garden-owned public images."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def _service_token() -> str:
    path = Path(settings.asset_service_token_file).expanduser()
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise GardenAssetError("Asset 服务凭据不可用") from exc
    if not token:
        raise GardenAssetError("Asset 服务凭据为空")
    return token


def upload_public_image(
    *,
    record_id: str,
    original_filename: str,
    content_type: str,
    content: bytes,
) -> GardenAssetUpload:
    """Upload an immutable original and bind it to a Garden media resource."""

    try:
        with AssetClient(settings.asset_base_url, _service_token()) as client:
            session = client.create_upload_session(
                owner_id=settings.asset_owner_id,
                ownership_mode="app_managed",
                access_mode="public",
                sensitivity="normal",
                original_filename=original_filename,
                content_type=content_type,
                size_bytes=len(content),
                display_name=original_filename,
                idempotency_key=f"garden:asset:{record_id}:upload",
            )
            client.upload_bytes(session["target"], content)
            asset = client.complete_upload(session["upload_session_id"])
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
        raise GardenAssetError("Asset 服务上传失败") from exc

    url = grant.get("url")
    if not isinstance(url, str) or not url:
        raise GardenAssetError("Asset 服务没有返回有效访问地址")
    return GardenAssetUpload(
        asset_id=str(asset["id"]),
        version_id=version_id,
        reference_id=str(reference["id"]),
        url=url,
    )
