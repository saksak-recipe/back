import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class UserInfoResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    nickname: str

    model_config = ConfigDict(from_attributes=True)


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
    info: UserInfoResponse
    access_token: str | None = Field(
        default=None, description="회원가입 후 즉시 로그인 시 발급되는 토큰"
    )


class LogInRequest(BaseModel):
    email: EmailStr = Field(..., description="로그인 이메일")
    password: str = Field(..., description="비밀번호")


class LogInResponse(BaseModel):
    info: UserInfoResponse
    access_token: str = Field(..., description="인증을 위한 액세스 토큰")
