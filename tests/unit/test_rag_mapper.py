from langchain_core.documents import Document

from domains.rag.mapper import (
    build_ingredient_query,
    classify_ingredients,
    map_document_to_recipe,
    parse_page_content,
    split_ingredient_names,
)


def test_build_ingredient_query():
    assert (
        build_ingredient_query(["계란", "양파"])
        == "parsed_ingredients: 계란, 양파"
    )


def test_parse_page_content():
    name, ingredients = parse_page_content(
        "recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 밥, 대파"
    )
    assert name == "계란볶음밥"
    assert ingredients == "계란, 밥, 대파"


def test_parse_page_content_missing_fields_returns_empty():
    name, ingredients = parse_page_content("garbage")
    assert name == ""
    assert ingredients == ""


def test_split_ingredient_names_dedupes_normalized():
    assert split_ingredient_names("김, 밥, 김, 참 기름, 참기름") == [
        "김",
        "밥",
        "참 기름",
    ]


def test_classify_ingredients_exact_normalized_match():
    owned, missing = classify_ingredients(
        ["김", "밥", "어묵", "대 파"],
        ["김", "대파", "계란"],
    )
    assert owned == ["김", "대 파"]
    assert missing == ["밥", "어묵"]


def test_classify_ingredients_synonym_match():
    owned, missing = classify_ingredients(["달걀", "밥"], ["계란"])
    assert owned == ["달걀"]
    assert missing == ["밥"]


def test_map_document_to_recipe():
    doc = Document(
        page_content="recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 밥, 대파",
        metadata={
            "board_name": "한식",
            "author_name": "kim",
            "recipe_difficulty": "초급",
            "time": "15분",
        },
    )
    recipe = map_document_to_recipe(doc, 0.42, owned_names=["계란", "양파"])
    assert recipe is not None
    assert recipe.recipe_name == "계란볶음밥"
    assert recipe.owned_ingredients == ["계란"]
    assert recipe.missing_ingredients == ["밥", "대파"]
    assert recipe.board_name == "한식"
    assert recipe.author_name == "kim"
    assert recipe.recipe_difficulty == "초급"
    assert recipe.time == "15분"
    assert recipe.score == 0.42


def test_map_document_skips_when_recipe_name_empty():
    doc = Document(page_content="parsed_ingredients: only", metadata={})
    assert map_document_to_recipe(doc, 0.1) is None


def test_map_document_reads_recipe_name_from_metadata():
    doc = Document(
        page_content="parsed_ingredients: 계란, 밥",
        metadata={"recipe_name": "계란볶음밥", "board_name": "한식"},
    )
    recipe = map_document_to_recipe(doc, 0.2, owned_names=["계란"])
    assert recipe is not None
    assert recipe.recipe_name == "계란볶음밥"
    assert recipe.owned_ingredients == ["계란"]
    assert recipe.missing_ingredients == ["밥"]


def test_is_recipe_name_in_ingredients():
    from domains.rag.mapper import is_recipe_name_in_ingredients

    assert is_recipe_name_in_ingredients("김가루", ["김가루", "계란"]) is True
    assert is_recipe_name_in_ingredients("김치볶음밥", ["김가루", "계란"]) is False
    assert is_recipe_name_in_ingredients("김 가루", ["김가루"]) is True
