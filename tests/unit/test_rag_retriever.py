from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

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
