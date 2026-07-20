from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.exception.exceptions import ExternalServiceException
from domains.recipe_detail.crawler import RecipeCrawler, parse_detail_html, parse_search_html

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_search_html_extracts_candidates():
    html = (FIXTURES / "10000recipe_search.html").read_text(encoding="utf-8")
    items = parse_search_html(html)
    assert len(items) == 2
    assert items[0].recipe_id == "6891574"
    assert "닭꼬치" in items[0].title
    assert items[0].author == "GP하루한끼"


def test_parse_search_html_reads_author_from_anchor():
    items = parse_search_html(
        """
        <li class="common_sp_list_li">
          <a class="common_sp_link" href="/recipe/6830820"></a>
          <div class="common_sp_caption_tit">갈치조림 레시피</div>
          <div class="common_sp_caption_rv_name">
            <a href="/profile/recipe.html?uid=x">
              <img src="https://example.com/a.jpg"/>요리하는최여사
            </a>
          </div>
        </li>
        """
    )
    assert items[0].recipe_id == "6830820"
    assert items[0].author == "요리하는최여사"


def test_parse_detail_html_from_ld_json():
    html = (FIXTURES / "10000recipe_detail.html").read_text(encoding="utf-8")
    detail = parse_detail_html(html, recipe_id="6891574")
    assert detail.recipe_name == "닭꼬치"
    assert detail.source_url == "https://www.10000recipe.com/recipe/6891574"
    assert detail.main_image_url == "https://example.com/main.jpg"
    assert detail.ingredients[0].name == "닭가슴살"
    assert detail.ingredients[0].amount == "200g"
    assert detail.steps[0].description == "재료를 준비한다."
    assert any("기름" in tip for tip in detail.tips)


def test_parse_detail_html_supports_recipe_type_array():
    detail = parse_detail_html(
        """
        <script type="application/ld+json">
          {"@type": ["Thing", "Recipe"], "name": "배열 레시피"}
        </script>
        """,
        recipe_id="1",
    )

    assert detail.recipe_name == "배열 레시피"


async def test_fetch_detail_rejects_empty_parsed_response():
    crawler = RecipeCrawler()
    crawler._get = AsyncMock(return_value="<html></html>")  # type: ignore[method-assign]

    with pytest.raises(ExternalServiceException):
        await crawler.fetch_detail("1")


def test_parse_detail_html_extracts_tips_from_view_step_tip():
    detail = parse_detail_html(
        """
        <html>
          <body>
            <dl class="view_step_tip">
              <dt>tip</dt>
              <dd>국물은 무와 다시마로 끓이면 깊은 맛이 나요.</dd>
            </dl>
          </body>
        </html>
        """,
        recipe_id="6830820",
    )

    assert detail.tips == ["국물은 무와 다시마로 끓이면 깊은 맛이 나요."]
