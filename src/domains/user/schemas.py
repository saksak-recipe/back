import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from domains.user.model import User


class UserInfoResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    nickname: str
    has_password: bool
    has_kakao: bool
    deleted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            email=user.email,
            nickname=user.nickname,
            has_password=user.password is not None,
            has_kakao=user.kakao_id is not None,
            deleted_at=user.deleted_at,
        )


class UpdateMeRequest(BaseModel):
    nickname: str | None = Field(
        default=None, min_length=2, max_length=20, description="닉네임 (2~20자)"
    )


class UpdatePasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=20)
    checked_password: str = Field(..., min_length=8, max_length=20)
    current_password: str | None = Field(default=None, min_length=8, max_length=20)

    @model_validator(mode="after")
    def verify_password_match(self):
        if self.new_password != self.checked_password:
            raise ValueError("비밀번호 확인이 일치하지 않습니다.")
        return self


class SignUpRequest(BaseModel):
    email: EmailStr = Field(
        ..., description="로그인 ID로 사용될 메일", examples=["user@example.com"]
    )
    password: str = Field(
        ..., min_length=8, max_length=20, description="비밀번호 (8~20자)"
    )
    checked_password: str = Field(
        ..., min_length=8, max_length=20, description="비밀번호 확인"
    )
    nickname: str = Field(
        ..., min_length=2, max_length=20, description="닉네임 (2~20자)"
    )

    @model_validator(mode="after")
    def verify_password_match(self):
        if self.password != self.checked_password:
            raise ValueError("비밀번호 확인이 일치하지 않습니다.")
        return self


class SignUpResponse(BaseModel):
    email: EmailStr
    message: str = "verification_code_sent"


class LogInRequest(BaseModel):
    email: EmailStr = Field(..., description="로그인 이메일")
    password: str = Field(..., description="비밀번호")


class LogInResponse(BaseModel):
    info: UserInfoResponse
    access_token: str = Field(..., description="인증을 위한 액세스 토큰")
    refresh_token: str = Field(..., description="액세스 토큰 갱신용 리프레시 토큰")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="리프레시 토큰")
