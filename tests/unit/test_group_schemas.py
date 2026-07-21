import pytest
from pydantic import ValidationError

from domains.group.schemas import (
    CreateGroupRequest,
    MergeRequest,
    UpdateGroupRequest,
)


def test_create_group_request_strips_name():
    req = CreateGroupRequest(name="  우리집  ")
    assert req.name == "우리집"


def test_create_group_request_rejects_empty_name():
    with pytest.raises(ValidationError):
        CreateGroupRequest(name="   ")


def test_create_group_request_rejects_name_over_40_chars():
    with pytest.raises(ValidationError):
        CreateGroupRequest(name="가" * 41)


def test_create_group_request_accepts_name_up_to_40_chars():
    name = "가" * 40
    req = CreateGroupRequest(name=name)
    assert req.name == name


def test_update_group_request_strips_and_validates_name():
    req = UpdateGroupRequest(name="  새이름  ")
    assert req.name == "새이름"

    with pytest.raises(ValidationError):
        UpdateGroupRequest(name="")


def test_merge_request_accepts_copy_and_move():
    copy_req = MergeRequest(mode="copy")
    move_req = MergeRequest(mode="move", ingredients=[1, 2], shopping_items=[3])
    assert copy_req.mode == "copy"
    assert move_req.mode == "move"
    assert move_req.ingredients == [1, 2]
    assert move_req.shopping_items == [3]


def test_merge_request_rejects_invalid_mode():
    with pytest.raises(ValidationError):
        MergeRequest(mode="sync")


def test_merge_request_defaults_empty_lists():
    req = MergeRequest(mode="copy")
    assert req.ingredients == []
    assert req.shopping_items == []
