from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from loguru import logger

from core.exception.exceptions import ExternalServiceException
from domains.auth.verification_store import PURPOSE_PASSWORD_RESET, PURPOSE_SIGNUP

_SUBJECT_BY_PURPOSE = {
    PURPOSE_SIGNUP: "회원가입 인증 코드",
    PURPOSE_PASSWORD_RESET: "비밀번호 재설정 인증 코드",
}


class EmailService:
    def __init__(
        self,
        backend: str = "console",
        *,
        smtp_host: str | None = None,
        smtp_port: int = 587,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        smtp_from_email: str | None = None,
        smtp_from_name: str = "삭삭",
        smtp_use_tls: bool = True,
    ) -> None:
        self._backend = backend
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._smtp_from_email = smtp_from_email
        self._smtp_from_name = smtp_from_name
        self._smtp_use_tls = smtp_use_tls

    async def send_verification_code(
        self, to_email: str, code: str, purpose: str
    ) -> None:
        if self._backend == "console":
            logger.info(
                "verification email to={} code={} purpose={}",
                to_email,
                code,
                purpose,
            )
            return
        if self._backend == "smtp":
            await asyncio.to_thread(
                self._send_smtp_verification_code, to_email, code, purpose
            )
            return
        raise ExternalServiceException(
            detail=f"지원하지 않는 이메일 백엔드입니다: {self._backend}"
        )

    def _send_smtp_verification_code(
        self, to_email: str, code: str, purpose: str
    ) -> None:
        if not self._smtp_host or not self._smtp_from_email:
            raise ExternalServiceException(
                detail="SMTP 설정이 누락되었습니다."
            )

        subject = _SUBJECT_BY_PURPOSE.get(purpose, "인증 코드")
        body = f"인증 코드: {code}\n\n이 코드는 3분간 유효합니다."

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self._smtp_from_name} <{self._smtp_from_email}>"
        message["To"] = to_email
        message.set_content(body)

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30) as smtp:
                if self._smtp_use_tls:
                    smtp.starttls()
                if self._smtp_user and self._smtp_password is not None:
                    smtp.login(self._smtp_user, self._smtp_password)
                smtp.send_message(message)
        except ExternalServiceException:
            raise
        except Exception as exc:
            raise ExternalServiceException(
                detail="이메일 발송에 실패했습니다."
            ) from exc
