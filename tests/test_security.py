from web.security import hash_password, verify_password


def test_password_hash_round_trip() -> None:
    password_hash = hash_password("s3cure-password")

    assert password_hash.startswith("pbkdf2_sha256$")
    assert verify_password("s3cure-password", password_hash=password_hash)
    assert not verify_password("wrong-password", password_hash=password_hash)


def test_plaintext_fallback_still_supported_for_local_development() -> None:
    assert verify_password("change-me-now", password_hash="", fallback_password="change-me-now")
    assert not verify_password("wrong-password", password_hash="", fallback_password="change-me-now")
