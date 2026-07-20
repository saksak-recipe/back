import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from core import security
from core.config import settings
from core.exception.exceptions import InvalidTokenException, TokenExpiredException


def test_hash_and_verify_password():
    hashed = security.hash_password("password123")

    assert hashed != "password123"
    assert security.verify_password("password123", hashed)
    assert not security.verify_password("wrong-password", hashed)


def test_create_and_decode_jwt():
    user_id = uuid.uuid4()
    token = security.create_jwt(user_id)

    decoded_id = security.decode_jwt(token)
    assert decoded_id == str(user_id)


def test_decode_jwt_raises_for_expired_token():
    payload = {
        "sub": str(uuid.uuid4()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()),
    }
    expired_token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(TokenExpiredException):
        security.decode_jwt(expired_token)


def test_decode_jwt_raises_for_invalid_token():
    with pytest.raises(InvalidTokenException):
        security.decode_jwt("invalid.token.value")


def test_kakao_signup_token_roundtrip():
    token = security.create_kakao_signup_token("1234567890")
    assert security.decode_kakao_signup_token(token) == "1234567890"


def test_kakao_signup_token_rejects_access_jwt():
    access = security.create_jwt(uuid.uuid4())
    with pytest.raises(InvalidTokenException):
        security.decode_kakao_signup_token(access)
