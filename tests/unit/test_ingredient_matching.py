from datetime import date, timedelta
from types import SimpleNamespace

from domains.ingredient_matching.matching import (
    classify_ingredients,
    names_match,
    normalize_name,
)
from domains.ingredient_matching.urgency import count_urgent_owned, urgent_names


def test_normalize_strips_casefold_spaces():
    assert normalize_name("  대 파 ") == "대파"
    assert normalize_name("Egg") == "egg"


def test_names_match_exact_normalized():
    assert names_match("대 파", "대파")


def test_names_match_synonym_egg():
    assert names_match("계란", "달걀")
    assert names_match("달걀", "계란")


def test_names_match_substring_min_len():
    assert names_match("달걀", "유기농달걀")
    assert not names_match("파", "대파")  # 1글자 부분일치 금지


def test_names_match_no_false_friend():
    assert not names_match("간장", "된장소스")


def test_classify_synonym_owned():
    owned, missing = classify_ingredients(
        ["달걀", "밥", "대파"],
        ["계란", "밥"],
    )
    assert owned == ["달걀", "밥"]
    assert missing == ["대파"]


def test_urgent_names_includes_soon_and_expired():
    today = date(2026, 7, 21)
    items = [
        SimpleNamespace(
            ingredient_name="우유",
            expiration_date=today - timedelta(days=1),
        ),
        SimpleNamespace(
            ingredient_name="계란",
            expiration_date=today + timedelta(days=2),
        ),
        SimpleNamespace(
            ingredient_name="양파",
            expiration_date=today + timedelta(days=10),
        ),
        SimpleNamespace(ingredient_name="김치", expiration_date=None),
    ]
    assert urgent_names(items, today=today) == ["우유", "계란"]


def test_count_urgent_owned_uses_names_match():
    assert count_urgent_owned(["달걀", "밥"], ["계란", "우유"]) == 1
