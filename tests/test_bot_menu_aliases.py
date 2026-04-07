from bot.keyboards import is_admin_menu_alias, is_worker_menu_alias, normalize_menu_trigger


def test_normalize_menu_trigger_collapses_case_and_spacing() -> None:
    assert normalize_menu_trigger("  MeNu   ") == "menu"
    assert normalize_menu_trigger("  Menu   Admin  ") == "menu admin"


def test_worker_menu_alias_accepts_plain_menu_only() -> None:
    assert is_worker_menu_alias("menu")
    assert is_worker_menu_alias("  MENU ")
    assert not is_worker_menu_alias("menu kehadiran")


def test_admin_menu_alias_accepts_plain_admin_only() -> None:
    assert is_admin_menu_alias("admin")
    assert is_admin_menu_alias("  ADMIN ")
    assert not is_admin_menu_alias("menu admin")
