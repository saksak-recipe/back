from core.exception.codes import ErrorCode
from core.exception.exceptions import NotificationNotFoundException


def test_notification_not_found_defaults():
    exc = NotificationNotFoundException()
    assert exc.status_code == 404
    assert exc.code == ErrorCode.NOTIFICATION_NOT_FOUND
    assert "알림" in exc.detail
