from fastapi import APIRouter, Depends, status

from api.deps import get_rag_service, get_recipe_detail_service
from core.exception.exceptions import (
    DatabaseException,
    ExternalServiceException,
    NotFoundException,
    TooManyRequestsException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.ingredient.scope import RecipeScope
from domains.rag.schemas import RecipeRecommendationResponse
from domains.rag.service import RagService
from domains.recipe_detail.schemas import RecipeDetailResponse
from domains.recipe_detail.service import RecipeDetailService

router = APIRouter(prefix="/recipes", tags=["레시피"])


@router.get(
    "/recommendations",
    status_code=status.HTTP_200_OK,
    response_model=RecipeRecommendationResponse,
    summary="레시피 추천",
    description="보유 재료 기반으로 레시피를 추천합니다. scope로 개인/그룹 재료를 선택할 수 있으며, 일일 사용량 제한이 있습니다.",
    responses=create_error_response(
        UnAuthorizedException,
        NotFoundException,
        ExternalServiceException,
        DatabaseException,
        TooManyRequestsException,
    ),
)
async def recommend_recipes(
    scope: RecipeScope = RecipeScope.personal,
    service: RagService = Depends(get_rag_service),
) -> RecipeRecommendationResponse:
    return await service.recommend_recipes(scope=scope)


@router.get(
    "/detail",
    status_code=status.HTTP_200_OK,
    summary="레시피 상세 조회",
    description="만개의 레시피 게시글명·작성자명으로 레시피 상세 정보를 크롤링해 반환합니다.",
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
