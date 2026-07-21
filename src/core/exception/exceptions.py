from core.exception.codes import ErrorCode


class BaseCustomException(Exception):
    def __init__(self, status_code: int, code: str | ErrorCode, detail: str):
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(detail)


# ----------------------------------------
# 1. 공통
# ----------------------------------------
class UnexpectedException(BaseCustomException):
    def __init__(self, detail: str = "서버 내부 오류"):
        super().__init__(
            status_code=500, code=ErrorCode.INTERNAL_SERVER_ERROR, detail=detail
        )


class DatabaseException(BaseCustomException):
    def __init__(self, detail: str = "데이터베이스 에러"):
        super().__init__(status_code=500, code=ErrorCode.DB_ERROR, detail=detail)


class BadRequestException(BaseCustomException):
    def __init__(
        self,
        code: str | ErrorCode = ErrorCode.BAD_REQUEST,
        detail: str = "잘못된 요청입니다.",
    ):
        super().__init__(status_code=400, code=code, detail=detail)


class UnAuthorizedException(BaseCustomException):
    def __init__(
        self,
        code: str | ErrorCode = ErrorCode.UNAUTHORIZED,
        detail: str = "인증이 필요합니다",
    ):
        super().__init__(status_code=401, code=code, detail=detail)


class ForbiddenException(BaseCustomException):
    def __init__(self, detail: str = "해당 작업에 대한 권한이 없습니다."):
        super().__init__(status_code=403, code=ErrorCode.FORBIDDEN, detail=detail)


class NotFoundException(BaseCustomException):
    def __init__(
        self,
        code: str | ErrorCode = ErrorCode.NOT_FOUND,
        detail: str = "요청하신 리소스를 찾을 수 없습니다.",
    ):
        super().__init__(status_code=404, code=code, detail=detail)


class ConflictException(BaseCustomException):
    def __init__(
        self,
        code: str | ErrorCode = ErrorCode.CONFLICT,
        detail: str = "리소스 충돌이 발생했습니다.",
    ):
        super().__init__(status_code=409, code=code, detail=detail)


class ExternalServiceException(BaseCustomException):
    def __init__(
        self,
        detail: str = "외부 서비스 연동 중 오류가 발생하였습니다.",
    ):
        super().__init__(
            status_code=502, code=ErrorCode.EXTERNAL_SERVICE_ERROR, detail=detail
        )


class TooManyRequestsException(BaseCustomException):
    def __init__(
        self,
        code: str | ErrorCode = ErrorCode.AI_QUOTA_EXCEEDED,
        detail: str = "오늘 AI 레시피 생성 한도(15회)를 초과했습니다.",
    ):
        super().__init__(status_code=429, code=code, detail=detail)


# ----------------------------------------
# 2. 토큰 관련
# ----------------------------------------
class TokenExpiredException(UnAuthorizedException):
    def __init__(
        self,
        detail: str = "토큰이 만료되었습니다. 다시 로그인하거나 토큰을 갱신해주세요",
    ):
        super().__init__(code=ErrorCode.TOKEN_EXPIRED, detail=detail)


class InvalidTokenException(UnAuthorizedException):
    def __init__(self, detail: str = "토큰이 변조되었거나 유효하지 않습니다."):
        super().__init__(code=ErrorCode.INVALID_TOKEN, detail=detail)


# ----------------------------------------
# 3. 회원 관련
# ----------------------------------------
class UserNotFoundException(NotFoundException):
    def __init__(self, detail: str = "사용자를 찾을 수 없습니다."):
        super().__init__(code=ErrorCode.USER_NOT_FOUND, detail=detail)


# ----------------------------------------
# 4. 식재료 관련
# ----------------------------------------
class IngredientNotFoundException(NotFoundException):
    def __init__(self, detail: str = "식재료를 찾을 수 없습니다."):
        super().__init__(code=ErrorCode.INGREDIENT_NOT_FOUND, detail=detail)


# ----------------------------------------
# 5. 장보기 관련
# ----------------------------------------
class ShoppingItemNotFoundException(NotFoundException):
    def __init__(self, detail: str = "장보기 항목을 찾을 수 없습니다."):
        super().__init__(code=ErrorCode.SHOPPING_ITEM_NOT_FOUND, detail=detail)
