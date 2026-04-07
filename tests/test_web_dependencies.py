from zoneinfo import ZoneInfo

import pytest

from web.dependencies import FormValidationError, parse_date, parse_datetime_local


LOCAL_TZ = ZoneInfo("Asia/Kuala_Lumpur")


def test_parse_date_accepts_iso_values() -> None:
    assert parse_date("2026-04-06").isoformat() == "2026-04-06"


def test_parse_date_rejects_invalid_values_with_friendly_error() -> None:
    with pytest.raises(FormValidationError, match="YYYY-MM-DD"):
        parse_date("06/04/2026")


def test_parse_datetime_local_rejects_invalid_values_with_friendly_error() -> None:
    with pytest.raises(FormValidationError, match="YYYY-MM-DDTHH:MM"):
        parse_datetime_local("2026-04-06 09:30")


def test_parse_datetime_local_returns_malaysia_timezone() -> None:
    parsed = parse_datetime_local("2026-04-06T09:30")

    assert parsed.isoformat() == "2026-04-06T09:30:00+08:00"
    assert parsed.tzinfo == LOCAL_TZ
