"""配置：全部来自环境变量，可选地从 server/.env 读取（不入库）。"""
import os
from pathlib import Path

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
    def admin_password(self) -> str:
        return os.environ.get("GARDEN_ADMIN_PASSWORD", "")

    @property
    def session_ttl_hours(self) -> int:
        return int(os.environ.get("GARDEN_SESSION_TTL_HOURS", "72"))

    @property
    def max_upload_mb(self) -> int:
        return int(os.environ.get("GARDEN_MAX_UPLOAD_MB", "8"))


settings = Settings()
