from domains.recipe_detail.matcher import SearchCandidate, pick_best_candidate
from domains.recipe_detail.normalize import normalize_text


def test_normalize_collapses_whitespace_and_case():
    assert normalize_text("  GP하루한끼  ") == "gp하루한끼"
    assert normalize_text("A  B") == "a b"


def test_pick_best_prefers_author_and_title_match():
    candidates = [
        SearchCandidate("1", "다른 요리", "다른작성자"),
        SearchCandidate(
            "6891574",
            "아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈",
            "GP하루한끼",
        ),
        SearchCandidate("2", "닭꼬치", "GP하루한끼"),
    ]
    best = pick_best_candidate(
        candidates,
        board_name="아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈",
        author_name="GP하루한끼",
    )
    assert best is not None
    assert best.recipe_id == "6891574"


def test_pick_best_returns_none_without_author_or_title_overlap():
    candidates = [
        SearchCandidate("1", "완전히 다른 제목", "다른사람"),
    ]
    assert (
        pick_best_candidate(candidates, "닭꼬치 레시피", "GP하루한끼") is None
    )
