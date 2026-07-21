from domains.ingredient_matching.matching import (
    classify_ingredients,
    names_match,
    normalize_name,
)


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
