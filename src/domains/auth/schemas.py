from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from core.quota import QuotaInfo
from domains.user.schemas import UserInfoResponse


class EmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class EmailResendRequest(BaseModel):
    email: EmailStr


class EmailResendResponse(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    ok: bool = True
    expires_in_seconds: int
    quota: QuotaInfo | None = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    ok: bool = True
    message: str = "password_reset_email_sent"


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    password: str = Field(
        ..., min_length=8, max_length=20, description="비밀번호 (8~20자)"
    )
    checked_password: str = Field(
        ..., min_length=8, max_length=20, description="비밀번호 확인"
    )

    @model_validator(mode="after")
    def verify_password_match(self):
        if self.password != self.checked_password:
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
    model_config = ConfigDict(exclude_none=True)

    email: EmailStr
    message: str = "verification_code_sent"
    expires_in_seconds: int = 180
    quota: QuotaInfo | None = None


class LogInRequest(BaseModel):
    email: EmailStr = Field(..., description="로그인 이메일")
    password: str = Field(..., description="비밀번호", min_length=8, max_length=20)


class LogInResponse(BaseModel):
    info: UserInfoResponse
    access_token: str = Field(..., description="인증을 위한 액세스 토큰")
    refresh_token: str = Field(..., description="액세스 토큰 갱신용 리프레시 토큰")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="리프레시 토큰")


class KakaoLoginRequest(BaseModel):
    access_token: str = Field(..., description="카카오 액세스 토큰")


class KakaoCompleteRequest(BaseModel):
    signup_token: str = Field(..., description="카카오 가입용 임시 토큰")
    nickname: str = Field(..., min_length=2, max_length=20, description="닉네임")
    email: EmailStr = Field(..., description="이메일")


class KakaoAuthResponse(BaseModel):
    status: Literal["authenticated"] = "authenticated"
    info: UserInfoResponse
    access_token: str
    refresh_token: str


class KakaoNeedsProfileResponse(BaseModel):
    status: Literal["needs_profile"] = "needs_profile"
    signup_token: str


class KakaoNeedsEmailVerificationResponse(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    status: Literal["needs_email_verification"] = "needs_email_verification"
    email: EmailStr
    message: str = "verification_code_sent"
    expires_in_seconds: int
    quota: QuotaInfo | None = None
