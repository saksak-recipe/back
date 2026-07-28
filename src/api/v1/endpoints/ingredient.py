from fastapi import APIRouter, status, Depends

from api.deps import get_ingredient_service
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    UnAuthorizedException,
    IngredientNotFoundException,
)
from core.exception.openapi import create_error_response
from domains.ingredient.schemas import (
    AddIngredientResponse,
    AddIngredientRequest,
    GetIngredientResponse,
    UpdateIngredientRequest,
)
from domains.ingredient.service import IngredientService

router = APIRouter(prefix="/ingredients", tags=["재료"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=list[AddIngredientResponse],
    summary="재료 추가",
    description="개인 냉장고에 재료를 하나 이상 추가합니다.",
    responses=create_error_response(
        UnAuthorizedException, BadRequestException, ConflictException
    ),
)
async def add_ingredients(
    request: AddIngredientRequest,
    service: IngredientService = Depends(get_ingredient_service),
) -> list[AddIngredientResponse]:
    return await service.add_ingredients(request)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[GetIngredientResponse],
    summary="재료 목록 조회",
    description="개인 냉장고에 등록된 재료 목록을 조회합니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def list_ingredients(
    service: IngredientService = Depends(get_ingredient_service),
) -> list[GetIngredientResponse]:
    return await service.get_ingredients()


@router.patch(
    "/{ingredient_id}",
    status_code=status.HTTP_200_OK,
    response_model=GetIngredientResponse,
    summary="재료 수정",
    description="개인 냉장고의 특정 재료 정보를 수정합니다.",
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        ConflictException,
        IngredientNotFoundException,
    ),
)
async def update_ingredient(
    ingredient_id: int,
    request: UpdateIngredientRequest,
    service: IngredientService = Depends(get_ingredient_service),
) -> GetIngredientResponse:
    return await service.update_ingredient(ingredient_id, request)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="재료 전체 삭제",
    description="개인 냉장고의 모든 재료를 삭제합니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def delete_all_ingredients(
    service: IngredientService = Depends(get_ingredient_service),
) -> None:
    await service.delete_all_ingredients()


@router.delete(
    "/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="재료 삭제",
    description="개인 냉장고의 특정 재료를 삭제합니다.",
    responses=create_error_response(
        UnAuthorizedException,
        IngredientNotFoundException,
    ),
)
async def delete_ingredient(
    ingredient_id: int,
    service: IngredientService = Depends(get_ingredient_service),
) -> None:
    await service.delete_ingredient(ingredient_id)
