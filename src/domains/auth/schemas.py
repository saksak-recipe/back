from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from domains.user.schemas import UserInfoResponse


class EmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class EmailResendRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    email: EmailStr


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
