from typing import Type
from core.exception.exceptions import BaseCustomException
from core.exception.schemas import GlobalErrorResponse


# Exception 클래스들을 받아서 Swagger responses 명세를 자동으로 생성해주는 함수
def create_error_response(*exception_classes: Type[BaseCustomException]):
    responses = {}

    for exc_class in exception_classes:
        # 1. 예외 클래스를 인스턴스화해서 default 값 추출
        exc = exc_class()

        status_code = exc.status_code

        # 2. 해당 status_code가 처음 나오면 기본 구조 생성
        if status_code not in responses:
            responses[status_code] = {
                "model": GlobalErrorResponse,
                "content": {"application/json": {"examples": {}}},
            }

        # 3. examples에 해당 예외 추가
        # 예: examples["DuplicateEmailException"] = { ... }
        responses[status_code]["content"]["application/json"]["examples"][
            exc_class.__name__
        ] = {
            "summary": exc.detail,  # Swagger UI 드롭다운에 표시될 이름
            "value": {
                "status_code": status_code,
                "code": exc.code,
                "detail": exc.detail,
            },
        }

    return responses
