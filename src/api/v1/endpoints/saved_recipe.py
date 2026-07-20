from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from api.deps import get_saved_recipe_service
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.saved_recipe.schemas import (
    SaveRecipeRequest,
    SavedRecipeDetailResponse,
    SavedRecipeListItem,
    SavedRecipeStatusResponse,
)
from domains.saved_recipe.service import SavedRecipeService

router = APIRouter(prefix="/recipes/saved", tags=["saved-recipes"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SavedRecipeDetailResponse,
    summary="레시피 저장",
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        NotFoundException,
        ConflictException,
        ExternalServiceException,
    ),
)
async def save_recipe(
    request: SaveRecipeRequest,
    service: SavedRecipeService = Depends(get_saved_recipe_service),
) -> SavedRecipeDetailResponse:
    return await service.save(request)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[SavedRecipeListItem],
    summary="저장 레시피 목록",
    responses=create_error_response(UnAuthorizedException),
)
async def list_saved_recipes(
    service: SavedRecipeService = Depends(get_saved_recipe_service),
) -> list[SavedRecipeListItem]:
    return await service.list_saved()


@router.get(
    "/status",
    status_code=status.HTTP_200_OK,
    response_model=SavedRecipeStatusResponse,
    summary="레시피 저장 여부",
    responses=create_error_response(UnAuthorizedException, BadRequestException),
)
async def saved_recipe_status(
    source: str = Query(...),
    source_id: str = Query(...),
    service: SavedRecipeService = Depends(get_saved_recipe_service),
) -> SavedRecipeStatusResponse:
    return await service.status(source, source_id)


@router.get(
    "/{recipe_id}",
    status_code=status.HTTP_200_OK,
    response_model=SavedRecipeDetailResponse,
    summary="저장 레시피 상세",
    responses=create_error_response(UnAuthorizedException, NotFoundException),
)
async def get_saved_recipe(
    recipe_id: UUID,
    service: SavedRecipeService = Depends(get_saved_recipe_service),
) -> SavedRecipeDetailResponse:
    return await service.get(recipe_id)


@router.delete(
    "/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="저장 레시피 삭제",
    responses=create_error_response(UnAuthorizedException, NotFoundException),
)
async def delete_saved_recipe(
    recipe_id: UUID,
    service: SavedRecipeService = Depends(get_saved_recipe_service),
) -> None:
    await service.delete(recipe_id)
