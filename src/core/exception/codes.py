from enum import StrEnum


class ErrorCode(StrEnum):
    # ----------------------------------------
    # 1. 공통
    # ----------------------------------------
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"  # 서버 내부 에러
    DB_ERROR = "DB_ERROR"  # 데이터베이스 오류
    HTTP_ERROR = "HTTP_ERROR"  # HTTP 에러
    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"  # Pydantic 모델 검증 실패 에러
    UNAUTHORIZED = "UNAUTHORIZED"  # 인증 필요 (로그인 안함)
    FORBIDDEN = "FORBIDDEN"  # 작업에 대한 권한 없음
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"

    # ----------------------------------------
    # 2. 토큰 관련
    # ----------------------------------------
    TOKEN_EXPIRED = "TOKEN_EXPIRED"  # 토큰 만료
    INVALID_TOKEN = "INVALID_TOKEN"  # 토큰이 유효하지 않거나 변조됨

    # ----------------------------------------
    # 3. 회원 관련
    # ----------------------------------------
    EMAIL_CONFLICT = "EMAIL_CONFLICT"  # 이메일 중복
    NICKNAME_CONFLICT = "NICKNAME_CONFLICT"  # 닉네임 중복
    PASSWORD_MISMATCH = "PASSWORD_MISMATCH"  # 비밀번호와 비밀번호 확인 불일치
    USER_NOT_FOUND = "USER_NOT_FOUND"  # 사용자 없음

    # ----------------------------------------
    # 4. 식재료 관련
    # ----------------------------------------
    INGREDIENT_NOT_FOUND = "INGREDIENT_NOT_FOUND"  # 식재료 없음
