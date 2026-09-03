"""Settings parsing behavior."""

from __future__ import annotations


def test_cors_origins_split_from_csv() -> None:
    """api_cors_origins is exposed as a trimmed list."""
    from app.config import Settings

    settings = Settings(api_cors_origins="http://a.test , http://b.test")

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_callback_allowlist_empty_when_unset() -> None:
    """An empty ASTRODEX_CALLBACK_URLS yields no allowed callback URLs."""
    from app.config import Settings

    settings = Settings(astrodex_callback_urls="")

    assert settings.callback_url_allowlist == []
