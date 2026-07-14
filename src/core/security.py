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
ACCESS_TOKEN_EXPIRE_MINUTES = 30
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

    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredException() from e
    except jwt.PyJWTError as e:
        raise InvalidTokenException() from e


def get_access_token(
    auth_header: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    if auth_header is None:
        raise UnAuthorizedException()
    return auth_header.credentials
