import pytest
from pydantic import ValidationError

from domains.saved_recipe.schemas import (
    SaveRecipeRequest,
    SavedRecipeStatusResponse,
)


def test_save_recipe_request_accepts_mangae_only():
    mangae = SaveRecipeRequest(source="mangae", source_id="보드|작성자")
    assert mangae.source == "mangae"


def test_save_recipe_request_rejects_ai():
    with pytest.raises(ValidationError):
        SaveRecipeRequest(source="ai", source_id="abc-123")


def test_status_response_shape():
    saved = SavedRecipeStatusResponse(saved=True, id="11111111-1111-1111-1111-111111111111")
    not_saved = SavedRecipeStatusResponse(saved=False, id=None)
    assert saved.saved is True
    assert not_saved.id is None
