from fastapi import APIRouter, Depends, status

from api.deps import (
    get_ai_recipe_service,
    get_rag_service,
    get_recipe_detail_service,
)
from core.exception.exceptions import (
    DatabaseException,
    ExternalServiceException,
    NotFoundException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.ai_recipe.schemas import (
    AiRecipeDetailResponse,
    AiRecipeRecommendationResponse,
)
from domains.ai_recipe.service import AiRecipeService
from domains.rag.schemas import RecipeRecommendationResponse
from domains.rag.service import RagService
from domains.recipe_detail.schemas import RecipeDetailResponse
from domains.recipe_detail.service import RecipeDetailService

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get(
    "/recommendations",
    status_code=status.HTTP_200_OK,
    response_model=RecipeRecommendationResponse,
    responses=create_error_response(
        UnAuthorizedException,
        ExternalServiceException,
        DatabaseException,
    ),
)
async def recommend_recipes(
    service: RagService = Depends(get_rag_service),
) -> RecipeRecommendationResponse:
    return await service.recommend_recipes()


@router.get(
    "/ai/recommendations",
    status_code=status.HTTP_200_OK,
    summary="AI 에이전트 레시피 추천",
    response_model=AiRecipeRecommendationResponse,
    responses=create_error_response(
        UnAuthorizedException,
        ExternalServiceException,
        DatabaseException,
    ),
)
async def ai_recommend_recipes(
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeRecommendationResponse:
    return await service.recommend()


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
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeDetailResponse:
    return await service.get_detail(recipe_id)


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
