from models.database import _postgres_is_textual_date_type, _postgres_safe_date_expression


def test_postgres_is_textual_date_type_identifies_textual_columns() -> None:
    assert _postgres_is_textual_date_type("text") is True
    assert _postgres_is_textual_date_type("character varying") is True
    assert _postgres_is_textual_date_type("date") is False


def test_postgres_safe_date_expression_guards_iso_date_casts() -> None:
    expression = _postgres_safe_date_expression("holiday_date")

    assert "CAST(holiday_date AS TEXT)" in expression
    assert "AS DATE" in expression
    assert "^[0-9]{4}-[0-9]{2}-[0-9]{2}$" in expression
