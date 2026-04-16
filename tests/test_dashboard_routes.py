from __future__ import annotations

from types import SimpleNamespace

from web.dashboard_routes import build_telegram_config_health


def test_build_telegram_config_health_flags_missing_mappings() -> None:
    sites = [
        SimpleNamespace(id=1, is_active=True, telegram_group_id=None),
        SimpleNamespace(id=2, is_active=True, telegram_group_id=-100123),
    ]
    workers = [
        SimpleNamespace(id=1, is_active=True, site_id=None, site=None),
        SimpleNamespace(id=2, is_active=True, site_id=1, site=SimpleNamespace(telegram_group_id=None)),
        SimpleNamespace(id=3, is_active=True, site_id=2, site=SimpleNamespace(telegram_group_id=-100123)),
    ]

    health = build_telegram_config_health(workers=workers, sites=sites)

    assert health["has_issues"] is True
    assert len(health["sites_missing_group"]) == 1
    assert len(health["workers_missing_site"]) == 1
    assert len(health["workers_missing_group_mapping"]) == 1
