from domains.saved_recipe.schemas import (
    SaveRecipeRequest,
    SavedRecipeStatusResponse,
)


def test_save_recipe_request_accepts_ai_and_mangae():
    ai = SaveRecipeRequest(source="ai", source_id="abc-123")
    mangae = SaveRecipeRequest(source="mangae", source_id="보드|작성자")
    assert ai.source == "ai"
    assert mangae.source == "mangae"


def test_status_response_shape():
    saved = SavedRecipeStatusResponse(saved=True, id="11111111-1111-1111-1111-111111111111")
    not_saved = SavedRecipeStatusResponse(saved=False, id=None)
    assert saved.saved is True
    assert not_saved.id is None
