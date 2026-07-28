from fastapi import APIRouter, Depends, status

from api.deps import get_shopping_service
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    ShoppingItemNotFoundException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.ingredient.schemas import AddIngredientResponse
from domains.shopping.schemas import (
    AddShoppingItemsRequest,
    ShoppingItemResponse,
    UpdateShoppingItemRequest,
)
from domains.shopping.service import ShoppingService

router = APIRouter(prefix="/shopping-items", tags=["장보기"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=list[ShoppingItemResponse],
    summary="장보기 항목 추가",
    description="개인 장보기 목록에 항목을 하나 이상 추가합니다.",
    responses=create_error_response(UnAuthorizedException, BadRequestException),
)
async def add_items(
    request: AddShoppingItemsRequest,
    service: ShoppingService = Depends(get_shopping_service),
) -> list[ShoppingItemResponse]:
    return await service.add_items(request)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[ShoppingItemResponse],
    summary="장보기 목록 조회",
    description="개인 장보기 목록을 조회합니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def list_items(
    service: ShoppingService = Depends(get_shopping_service),
) -> list[ShoppingItemResponse]:
    return await service.list_items()


@router.patch(
    "/{item_id}",
    status_code=status.HTTP_200_OK,
    response_model=ShoppingItemResponse,
    summary="장보기 항목 수정",
    description="개인 장보기 목록의 특정 항목을 수정합니다.",
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        ShoppingItemNotFoundException,
    ),
)
async def update_item(
    item_id: int,
    request: UpdateShoppingItemRequest,
    service: ShoppingService = Depends(get_shopping_service),
) -> ShoppingItemResponse:
    return await service.update_item(item_id, request)


@router.post(
    "/{item_id}/to-ingredient",
    status_code=status.HTTP_201_CREATED,
    response_model=AddIngredientResponse,
    summary="장보기 항목을 재료로 전환",
    description="장보기 항목을 개인 냉장고 재료로 옮기고 해당 장보기 항목을 제거합니다.",
    responses=create_error_response(
        UnAuthorizedException,
        ConflictException,
        ShoppingItemNotFoundException,
    ),
)
async def to_ingredient(
    item_id: int,
    service: ShoppingService = Depends(get_shopping_service),
) -> AddIngredientResponse:
    return await service.to_ingredient(item_id)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="장보기 전체 삭제",
    description="개인 장보기 목록의 모든 항목을 삭제합니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def delete_all(
    service: ShoppingService = Depends(get_shopping_service),
) -> None:
    await service.delete_all()


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="장보기 항목 삭제",
    description="개인 장보기 목록의 특정 항목을 삭제합니다.",
    responses=create_error_response(
        UnAuthorizedException,
        ShoppingItemNotFoundException,
    ),
)
async def delete_item(
    item_id: int,
    service: ShoppingService = Depends(get_shopping_service),
) -> None:
    await service.delete_item(item_id)
