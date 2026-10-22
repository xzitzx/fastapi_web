import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

REQUIRED_VARS = ("SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD_HASH")


@dataclass(frozen=True)
class Settings:
    secret_key: str
    admin_username: str
    admin_password_hash: str
    database_url: str
    media_root: Path


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    missing = [name for name in REQUIRED_VARS if not env.get(name, "").strip()]
    if missing:
        raise RuntimeError(f"缺少必要的环境变量：{', '.join(missing)}")
    return Settings(
        secret_key=env["SECRET_KEY"],
        admin_username=env["ADMIN_USERNAME"],
        admin_password_hash=env["ADMIN_PASSWORD_HASH"],
        database_url=env.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'blog.db'}",
        media_root=Path(env.get("MEDIA_ROOT") or BASE_DIR / "media"),
    )


settings = load_settings()
