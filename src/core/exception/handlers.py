from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.exception.codes import ErrorCode
from core.exception.exceptions import BaseCustomException


async def custom_exception_handler(request: Request, exc: BaseCustomException):
    """비즈니스 로직에서 발생하는 커스텀 예외 처리"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status_code": exc.status_code,
            "code": exc.code,
            "detail": exc.detail,
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Starlette 및 FastAPI 기본 HTTPException 처리"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status_code": exc.status_code,
            "code": ErrorCode.HTTP_ERROR,
            "detail": exc.detail,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 모델 검증 실패(422) 처리"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(
            {
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "code": ErrorCode.VALIDATION_ERROR,
                "detail": exc.errors(),
            }
        ),
    )


async def system_exception_handler(request: Request, exc: Exception):
    """그 외 정의되지 않은 모든 서버 내부 에러(500) 처리"""
    logger.exception(
        f"예상치 못한 서버 에러 발생! URL: {request.method} {request.url.path}"
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status_code": 500,
            "code": ErrorCode.INTERNAL_SERVER_ERROR,
            "detail": "서버 내부 오류가 발생했습니다. 관리자에게 문의하세요.",
        },
    )
