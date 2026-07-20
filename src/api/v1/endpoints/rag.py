from fastapi import APIRouter, Depends, status

from api.deps import get_rag_service
from core.exception.exceptions import (
    DatabaseException,
    ExternalServiceException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.rag.schemas import RecipeRecommendationResponse
from domains.rag.service import RagService

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
