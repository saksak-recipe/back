import hashlib
import secrets
import uuid

import jwt
from datetime import datetime, timezone, timedelta

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from core.config import settings
from core.exception.exceptions import (
    TokenExpiredException,
    InvalidTokenException,
    UnAuthorizedException,
)

# 설정 및 상수
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_SECONDS = 14 * 24 * 60 * 60
KAKAO_SIGNUP_TOKEN_EXPIRE_MINUTES = 10
KAKAO_SIGNUP_PURPOSE = "kakao_signup"
JWT_SECRET_KEY = settings.JWT_SECRET_KEY.get_secret_value()
JWT_ALGORITHM = "HS256"

# 인스턴스 초기화
password_hasher = PasswordHash((Argon2Hasher(),))
security_scheme = HTTPBearer(auto_error=False)


# 비밀번호 관련
def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# JWT 토큰 관련
def create_jwt(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_jwt(access_token: str) -> str:
    try:
        payload = jwt.decode(access_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            raise TokenExpiredException("유효하지 않은 토큰입니다.")
        return user_id

    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredException() from e
    except jwt.PyJWTError as e:
        raise InvalidTokenException() from e


def create_kakao_signup_token(kakao_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": kakao_id,
        "purpose": KAKAO_SIGNUP_PURPOSE,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=KAKAO_SIGNUP_TOKEN_EXPIRE_MINUTES)).timestamp()
        ),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_kakao_signup_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != KAKAO_SIGNUP_PURPOSE:
            raise InvalidTokenException(detail="유효하지 않은 가입 토큰입니다.")
        kakao_id = payload.get("sub")
        if not kakao_id:
            raise InvalidTokenException(detail="유효하지 않은 가입 토큰입니다.")
        return str(kakao_id)
    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredException(detail="가입 토큰이 만료되었습니다.") from e
    except jwt.PyJWTError as e:
        raise InvalidTokenException(detail="유효하지 않은 가입 토큰입니다.") from e


def get_access_token(
    auth_header: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    if auth_header is None:
        raise UnAuthorizedException()
    return auth_header.credentials
