from fastapi import APIRouter, status, Depends

from api.deps import get_ingredient_service
from core.exception.exceptions import (
    BadRequestException,
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

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=list[AddIngredientResponse],
    responses=create_error_response(UnAuthorizedException, BadRequestException),
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
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
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
    responses=create_error_response(
        UnAuthorizedException,
        IngredientNotFoundException,
    ),
)
async def delete_all_ingredients(
    service: IngredientService = Depends(get_ingredient_service),
) -> None:
    await service.delete_all_ingredients()


@router.delete(
    "/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
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
