from collections.abc import AsyncIterator
import json

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from api.deps import (
    get_ai_recipe_service,
    get_rag_service,
    get_recipe_detail_service,
)
from core.exception.exceptions import (
    DatabaseException,
    ExternalServiceException,
    NotFoundException,
    TooManyRequestsException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.ai_recipe.schemas import (
    AiRecipeDetailResponse,
    AiRecipeRecommendationResponse,
)
from domains.ai_recipe.service import AiRecipeService
from domains.ingredient.scope import RecipeScope
from domains.rag.schemas import RecipeRecommendationResponse
from domains.rag.service import RagService
from domains.recipe_detail.schemas import RecipeDetailResponse
from domains.recipe_detail.service import RecipeDetailService

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get(
    "/recommendations",
    status_code=status.HTTP_200_OK,
    response_model=RecipeRecommendationResponse,
    responses=create_error_response(
        UnAuthorizedException,
        NotFoundException,
        ExternalServiceException,
        DatabaseException,
    ),
)
async def recommend_recipes(
    scope: RecipeScope = RecipeScope.personal,
    service: RagService = Depends(get_rag_service),
) -> RecipeRecommendationResponse:
    return await service.recommend_recipes(scope=scope)


@router.get(
    "/ai/recommendations",
    status_code=status.HTTP_200_OK,
    summary="AI 에이전트 레시피 추천",
    response_model=AiRecipeRecommendationResponse,
    responses=create_error_response(
        UnAuthorizedException,
        NotFoundException,
        ExternalServiceException,
        DatabaseException,
    ),
)
async def ai_recommend_recipes(
    refresh: bool = False,
    scope: RecipeScope = RecipeScope.personal,
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeRecommendationResponse:
    return await service.recommend(refresh=refresh, scope=scope)


@router.get(
    "/ai/detail",
    status_code=status.HTTP_200_OK,
    summary="AI 에이전트 레시피 상세",
    response_model=AiRecipeDetailResponse,
    responses=create_error_response(
        UnAuthorizedException,
        NotFoundException,
        ExternalServiceException,
    ),
)
async def ai_recipe_detail(
    recipe_id: str,
    scope: RecipeScope = RecipeScope.personal,
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeDetailResponse:
    return await service.get_detail(recipe_id, scope=scope)


@router.get(
    "/ai/detail/stream",
    status_code=status.HTTP_200_OK,
    summary="AI 에이전트 레시피 상세 (SSE)",
    responses=create_error_response(
        UnAuthorizedException,
        NotFoundException,
        TooManyRequestsException,
        ExternalServiceException,
    ),
)
async def ai_recipe_detail_stream(
    recipe_id: str,
    scope: RecipeScope = RecipeScope.personal,
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> StreamingResponse:
    stream = service.stream_detail(recipe_id, scope=scope)
    try:
        first = await anext(stream)
    except NotFoundException:
        raise
    except TooManyRequestsException:
        raise

    async def gen() -> AsyncIterator[str]:
        name, payload = first
        yield _sse(name, payload)
        async for name, payload in stream:
            yield _sse(name, payload)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get(
    "/detail",
    status_code=status.HTTP_200_OK,
    summary="만개의 레시피 기반 크롤링 검색",
    response_model=RecipeDetailResponse,
    responses=create_error_response(
        UnAuthorizedException,
        NotFoundException,
        ExternalServiceException,
    ),
)
async def recipe_detail(
    board_name: str,
    author_name: str,
    service: RecipeDetailService = Depends(get_recipe_detail_service),
) -> RecipeDetailResponse:
    return await service.get_detail(board_name, author_name)
