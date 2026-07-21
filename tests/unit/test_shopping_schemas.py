import pytest
from pydantic import ValidationError

from domains.shopping.schemas import AddShoppingItemsRequest, UpdateShoppingItemRequest


def test_add_request_strips_names():
    req = AddShoppingItemsRequest(names=["  대파  ", "계란"])
    assert req.names == ["대파", "계란"]


def test_add_request_rejects_empty_list():
    with pytest.raises(ValidationError):
        AddShoppingItemsRequest(names=[])


def test_add_request_rejects_blank_name():
    with pytest.raises(ValidationError):
        AddShoppingItemsRequest(names=["  "])


def test_add_request_rejects_too_long_name():
    with pytest.raises(ValidationError):
        AddShoppingItemsRequest(names=["가" * 46])


def test_update_request_requires_is_checked():
    req = UpdateShoppingItemRequest(is_checked=True)
    assert req.is_checked is True
