from core.exception.codes import ErrorCode
from core.exception.exceptions import TooManyRequestsException


def test_too_many_requests_exception_defaults():
    exc = TooManyRequestsException()
    assert exc.status_code == 429
    assert exc.code == ErrorCode.AI_QUOTA_EXCEEDED
    assert "한도" in exc.detail
