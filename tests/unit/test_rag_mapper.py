from langchain_core.documents import Document

from domains.rag.mapper import (
    build_ingredient_query,
    map_document_to_recipe,
    parse_page_content,
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


def test_map_document_to_recipe():
    doc = Document(
        page_content="recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 밥",
        metadata={
            "board_name": "한식",
            "author_name": "kim",
            "recipe_difficulty": "초급",
            "time": "15분",
        },
    )
    recipe = map_document_to_recipe(doc, 0.42)
    assert recipe is not None
    assert recipe.recipe_name == "계란볶음밥"
    assert recipe.parsed_ingredients == "계란, 밥"
    assert recipe.board_name == "한식"
    assert recipe.author_name == "kim"
    assert recipe.recipe_difficulty == "초급"
    assert recipe.time == "15분"
    assert recipe.score == 0.42


def test_map_document_skips_when_recipe_name_empty():
    doc = Document(page_content="parsed_ingredients: only", metadata={})
    assert map_document_to_recipe(doc, 0.1) is None
