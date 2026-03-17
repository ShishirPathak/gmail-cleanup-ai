from app.core.security import create_access_token, decode_access_token, decrypt_secret, encrypt_secret


def test_token_round_trip():
    token = create_access_token("123")
    payload = decode_access_token(token)
    assert payload["sub"] == "123"


def test_secret_round_trip():
    value = "top-secret"
    encrypted = encrypt_secret(value)
    assert encrypted != value
    assert decrypt_secret(encrypted) == value
