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
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    INVALID_VERIFICATION_CODE = "INVALID_VERIFICATION_CODE"
    VERIFICATION_COOLDOWN = "VERIFICATION_COOLDOWN"
    EMAIL_ALREADY_VERIFIED = "EMAIL_ALREADY_VERIFIED"

    # ----------------------------------------
    # 3-1. 그룹 관련
    # ----------------------------------------
    ALREADY_IN_GROUP = "ALREADY_IN_GROUP"
    GROUP_NOT_FOUND = "GROUP_NOT_FOUND"
    INVITE_CODE_INVALID = "INVITE_CODE_INVALID"
    INVALID_INVITE = "INVALID_INVITE"
    OWNER_CANNOT_LEAVE = "OWNER_CANNOT_LEAVE"
    INGREDIENT_NAME_CONFLICT = "INGREDIENT_NAME_CONFLICT"

    # ----------------------------------------
    # 4. 식재료 관련
    # ----------------------------------------
    INGREDIENT_NOT_FOUND = "INGREDIENT_NOT_FOUND"  # 식재료 없음

    # ----------------------------------------
    # 5. 장보기 관련
    # ----------------------------------------
    SHOPPING_ITEM_NOT_FOUND = "SHOPPING_ITEM_NOT_FOUND"  # 장보기 항목 없음

    # ----------------------------------------
    # 6. 알림 관련
    # ----------------------------------------
    NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"
