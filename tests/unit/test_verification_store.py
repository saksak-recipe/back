import asyncio

import fakeredis.aioredis
import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import BadRequestException
from domains.auth import verification_store
from domains.auth.verification_store import (
    PURPOSE_SIGNUP,
    VerificationCodeStore,
)


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = VerificationCodeStore(redis)
    yield s
    await redis.aclose()


async def test_issue_and_verify_success(store: VerificationCodeStore):
    code = await store.issue(PURPOSE_SIGNUP, "a@example.com")
    assert len(code) == 6 and code.isdigit()
    await store.verify(PURPOSE_SIGNUP, "a@example.com", code)


async def test_verify_wrong_code_raises(store: VerificationCodeStore):
    await store.issue(PURPOSE_SIGNUP, "a@example.com")
    with pytest.raises(BadRequestException) as ei:
        await store.verify(PURPOSE_SIGNUP, "a@example.com", "000000")
    assert ei.value.code == ErrorCode.INVALID_VERIFICATION_CODE


async def test_cooldown_blocks_reissue(store: VerificationCodeStore):
    await store.issue(PURPOSE_SIGNUP, "a@example.com")
    with pytest.raises(BadRequestException) as ei:
        await store.issue(PURPOSE_SIGNUP, "a@example.com")
    assert ei.value.code == ErrorCode.VERIFICATION_COOLDOWN


async def test_five_failures_invalidate_code(
    store: VerificationCodeStore,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        verification_store,
        "generate_email_code",
        lambda: "123456",
    )
    await store.issue(PURPOSE_SIGNUP, "a@example.com")

    for _ in range(5):
        with pytest.raises(BadRequestException) as ei:
            await store.verify(PURPOSE_SIGNUP, "a@example.com", "999999")
        assert ei.value.code == ErrorCode.INVALID_VERIFICATION_CODE

    with pytest.raises(BadRequestException) as ei:
        await store.verify(PURPOSE_SIGNUP, "a@example.com", "123456")
    assert ei.value.code == ErrorCode.INVALID_VERIFICATION_CODE


async def test_concurrent_issue_allows_only_one_code(
    store: VerificationCodeStore,
    monkeypatch: pytest.MonkeyPatch,
):
    codes = iter(("111111", "222222"))
    monkeypatch.setattr(
        verification_store,
        "generate_email_code",
        lambda: next(codes),
    )

    results = await asyncio.gather(
        store.issue(PURPOSE_SIGNUP, "a@example.com"),
        store.issue(PURPOSE_SIGNUP, "a@example.com"),
        return_exceptions=True,
    )

    issued_codes = [result for result in results if isinstance(result, str)]
    errors = [
        result for result in results if isinstance(result, BadRequestException)
    ]
    assert len(issued_codes) == 1
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.VERIFICATION_COOLDOWN
    await store.verify(PURPOSE_SIGNUP, "a@example.com", issued_codes[0])
