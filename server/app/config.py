"""配置：全部来自环境变量，可选地从 server/.env 读取（不入库）。"""
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

BASE_DIR = Path(__file__).resolve().parent.parent   # server/
SITE_DIR = BASE_DIR.parent / "site"

ENV_FILE = BASE_DIR / ".env"


def _load_env_file() -> None:
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


class Settings:
    """属性都在访问时读环境变量，便于测试覆盖。"""

    @property
    def data_dir(self) -> Path:
        return Path(os.environ.get("GARDEN_DATA_DIR", str(BASE_DIR / "data")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "garden.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def db_url(self) -> str:
        """postgresql://user:pw@host/db 走 PostgreSQL；留空用本地 SQLite。"""
        return os.environ.get("GARDEN_DB_URL", "")

    @property
    def redis_url(self) -> str:
        """redis://host:port/db；配置后会话与登录限流走 Redis，留空用数据库表。"""
        return os.environ.get("GARDEN_REDIS_URL", "")

    @property
    def agent_token(self) -> str:
        return os.environ.get("GARDEN_AGENT_TOKEN", "")

    @property
    def canonical_url(self) -> str:
        return os.environ.get("GARDEN_CANONICAL_URL", "").rstrip("/")

    @property
    def oidc_issuer(self) -> str:
        return os.environ.get("GARDEN_OIDC_ISSUER", "").rstrip("/")

    @property
    def oidc_client_id(self) -> str:
        return os.environ.get("GARDEN_OIDC_CLIENT_ID", "shadow-garden")

    @property
    def oidc_client_secret_file(self) -> str:
        return os.environ.get("GARDEN_OIDC_CLIENT_SECRET_FILE", "")

    @property
    def oidc_redirect_uri(self) -> str:
        return os.environ.get("GARDEN_OIDC_REDIRECT_URI", "")

    @property
    def oidc_post_logout_redirect_uri(self) -> str:
        return os.environ.get("GARDEN_OIDC_POST_LOGOUT_REDIRECT_URI", "")

    @property
    def oidc_required_group(self) -> str:
        return os.environ.get("GARDEN_OIDC_REQUIRED_GROUP", "garden-admins")

    @property
    def oidc_session_db(self) -> str:
        return os.environ.get(
            "GARDEN_OIDC_SESSION_DB", str(self.data_dir / "web_auth.db")
        )

    @property
    def oidc_session_ttl_seconds(self) -> int:
        return int(os.environ.get("GARDEN_OIDC_SESSION_TTL_SECONDS", "43200"))

    @property
    def max_upload_mb(self) -> int:
        return int(os.environ.get("GARDEN_MAX_UPLOAD_MB", "8"))

    @property
    def asset_mode(self) -> str:
        return os.environ.get("GARDEN_ASSET_MODE", "platform").strip().lower()

    @property
    def asset_base_url(self) -> str:
        return os.environ.get("GARDEN_ASSET_BASE_URL", "").rstrip("/")

    @property
    def asset_service_token_file(self) -> str:
        return os.environ.get("GARDEN_ASSET_SERVICE_TOKEN_FILE", "")

    @property
    def asset_owner_id(self) -> str:
        return os.environ.get("GARDEN_ASSET_OWNER_ID", "").strip()

    def validate_asset_config(self) -> None:
        if self.asset_mode == "local":
            return
        if self.asset_mode != "platform":
            raise ValueError("GARDEN_ASSET_MODE must be platform or local")
        parsed = urlsplit(self.asset_base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {
            "127.0.0.1",
            "localhost",
            "testserver",
        }
        if not parsed.hostname or (parsed.scheme != "https" and not local_http):
            raise ValueError("GARDEN_ASSET_BASE_URL must use HTTPS except locally")
        token_file = Path(self.asset_service_token_file).expanduser()
        if not token_file.is_file():
            raise ValueError("GARDEN_ASSET_SERVICE_TOKEN_FILE is unavailable")
        try:
            UUID(self.asset_owner_id)
        except ValueError as exc:
            raise ValueError("GARDEN_ASSET_OWNER_ID must be a UUID") from exc


settings = Settings()
