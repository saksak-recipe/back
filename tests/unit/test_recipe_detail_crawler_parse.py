from pathlib import Path

from domains.recipe_detail.crawler import parse_detail_html, parse_search_html

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_search_html_extracts_candidates():
    html = (FIXTURES / "10000recipe_search.html").read_text(encoding="utf-8")
    items = parse_search_html(html)
    assert len(items) == 2
    assert items[0].recipe_id == "6891574"
    assert "닭꼬치" in items[0].title
    assert items[0].author == "GP하루한끼"


def test_parse_detail_html_from_ld_json():
    html = (FIXTURES / "10000recipe_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_html(html, recipe_id="6891574")
    assert detail.recipe_name == "닭꼬치"
    assert detail.source_url == "https://www.10000recipe.com/recipe/6891574"
    assert detail.main_image_url == "https://example.com/main.jpg"
    assert detail.ingredients[0].name == "닭가슴살"
    assert detail.ingredients[0].amount == "200g"
    assert detail.steps[0].description == "재료를 준비한다."
    assert detail.steps[0].image_url == "https://example.com/s1.jpg"
    assert any("기름" in t for t in detail.tips) or (
        detail.steps[0].tip is not None and "기름" in detail.steps[0].tip
    )
