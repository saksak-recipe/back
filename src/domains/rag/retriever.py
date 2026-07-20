from functools import lru_cache

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from core.config import settings
from core.exception.exceptions import DatabaseException, ExternalServiceException


class RecipeRetriever:
    def __init__(self, vector_store: PGVector):
        self._vector_store = vector_store

    def search(self, query: str, k: int = 5) -> list[tuple[Document, float]]:
        try:
            return self._vector_store.similarity_search_with_score(query, k=k)
        except Exception as e:
            message = str(e).lower()
            if "openai" in message or "embedding" in message or "api" in message:
                raise ExternalServiceException(
                    detail="레시피 임베딩 요청 중 오류가 발생했습니다."
                ) from e
            raise DatabaseException(
                detail="레시피 벡터 검색 중 DB 오류가 발생했습니다."
            ) from e


@lru_cache
def get_recipe_retriever() -> RecipeRetriever:
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.OPENAI_API_KEY.get_secret_value(),
    )
    vector_store = PGVector(
        embeddings=embeddings,
        connection=settings.database_rag_sync_url,
        collection_name="recipe_vectors",
    )
    return RecipeRetriever(vector_store=vector_store)
