from unittest.mock import MagicMock

import openai
import psycopg
import pytest
from httpx import Request
from langchain_core.documents import Document

from core.exception.exceptions import DatabaseException, ExternalServiceException
from domains.rag.retriever import RecipeRetriever


def test_search_delegates_to_vector_store():
    store = MagicMock()
    doc = Document(page_content="recipe_name: a\nparsed_ingredients: b")
    store.similarity_search_with_score.return_value = [(doc, 0.3)]

    retriever = RecipeRetriever(vector_store=store)
    result = retriever.search("parsed_ingredients: 계란", k=5)

    store.similarity_search_with_score.assert_called_once_with(
        "parsed_ingredients: 계란", k=5
    )
    assert result == [(doc, 0.3)]


def test_search_openai_error_raises_external_service_exception():
    store = MagicMock()
    request = Request("POST", "https://api.openai.com/v1/embeddings")
    store.similarity_search_with_score.side_effect = openai.APIError(
        "embedding failed",
        request=request,
        body=None,
    )

    retriever = RecipeRetriever(vector_store=store)

    with pytest.raises(ExternalServiceException) as exc_info:
        retriever.search("parsed_ingredients: 계란")

    assert exc_info.value.detail == "레시피 임베딩 요청 중 오류가 발생했습니다."
    assert isinstance(exc_info.value.__cause__, openai.APIError)


def test_search_db_error_raises_database_exception():
    store = MagicMock()
    store.similarity_search_with_score.side_effect = psycopg.OperationalError(
        "connection failed"
    )

    retriever = RecipeRetriever(vector_store=store)

    with pytest.raises(DatabaseException) as exc_info:
        retriever.search("parsed_ingredients: 계란")

    assert exc_info.value.detail == "레시피 벡터 검색 중 DB 오류가 발생했습니다."
    assert isinstance(exc_info.value.__cause__, psycopg.Error)
