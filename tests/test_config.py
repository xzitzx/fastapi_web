from pathlib import Path

import pytest

from app.config import BASE_DIR, load_settings

REQUIRED = {"SECRET_KEY": "k", "ADMIN_USERNAME": "admin", "ADMIN_PASSWORD_HASH": "h"}


def test_missing_secret_key():
    """Scenario: 缺少 SECRET_KEY"""
    env = {k: v for k, v in REQUIRED.items() if k != "SECRET_KEY"}

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_settings(env)


def test_lists_every_missing_or_empty_variable():
    with pytest.raises(RuntimeError) as exc:
        load_settings({"SECRET_KEY": ""})

    for name in REQUIRED:
        assert name in str(exc.value)


def test_whitespace_only_counts_as_missing():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_settings({**REQUIRED, "SECRET_KEY": "  "})


def test_defaults():
    settings = load_settings(REQUIRED)

    assert BASE_DIR == Path(__file__).resolve().parent.parent
    assert settings.secret_key == "k"
    assert settings.admin_username == "admin"
    assert settings.admin_password_hash == "h"
    assert settings.database_url == f"sqlite:///{BASE_DIR / 'blog.db'}"
    assert settings.media_root == BASE_DIR / "media"


def test_overrides():
    settings = load_settings(
        {**REQUIRED, "DATABASE_URL": "sqlite:////tmp/x.db", "MEDIA_ROOT": "/tmp/m"}
    )

    assert settings.database_url == "sqlite:////tmp/x.db"
    assert settings.media_root == Path("/tmp/m")
