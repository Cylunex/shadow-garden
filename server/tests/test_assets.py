from app import assets


def test_asset_upload_uses_v1_sdk_contract(tmp_path, monkeypatch):
    token_file = tmp_path / "asset-token"
    token_file.write_text("garden-platform-token", encoding="utf-8")
    monkeypatch.setenv("GARDEN_ASSET_MODE", "platform")
    monkeypatch.setenv("GARDEN_ASSET_BASE_URL", "https://assets.example.test")
    monkeypatch.setenv("GARDEN_ASSET_SERVICE_TOKEN_FILE", str(token_file))
    monkeypatch.setenv(
        "GARDEN_ASSET_OWNER_ID", "10000000-0000-4000-8000-000000000001"
    )
    assets.settings.validate_asset_config()
    calls = []

    class FakeAssetClient:
        def __init__(self, base_url, token):
            assert base_url == "https://assets.example.test"
            assert token == "garden-platform-token"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def create_upload_session(self, **kwargs):
            calls.append(("create", kwargs))
            return {
                "upload_session_id": "upload-1",
                "expires_at": "2026-08-20T00:00:00+00:00",
                "target": {"method": "PUT", "url": "https://upload.example.test"},
            }

        def upload_bytes(self, target, content):
            calls.append(("upload", target, content))

        def complete_upload(self, upload_session_id):
            assert upload_session_id == "upload-1"
            return {"id": "asset-1", "current_version_id": "version-1"}

        def create_reference(self, **kwargs):
            calls.append(("reference", kwargs))
            return {"id": "reference-1"}

        def grant_access(self, version_id, *, operation):
            assert (version_id, operation) == ("version-1", "inline")
            return {"url": "https://assets.example.test/public/version-1"}

    monkeypatch.setattr(assets, "AssetClient", FakeAssetClient)
    result = assets.upload_public_image(
        record_id="file-1",
        original_filename="photo.png",
        content_type="image/png",
        content=b"png-data",
    )

    assert result.asset_id == "asset-1"
    assert result.reference_id == "reference-1"
    assert result.url == "https://assets.example.test/public/version-1"
    assert calls[0][1]["access_mode"] == "public"
    assert calls[0][1]["ownership_mode"] == "app_managed"
    assert calls[2][1]["resource_uri"] == "shadow://garden/assets/file-1"
    assert calls[2][1]["pinned_version_id"] == "version-1"
