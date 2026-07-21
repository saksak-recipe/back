from uuid import UUID

from fastapi import APIRouter, Depends, status

from api.deps import get_group_service
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    IngredientNotFoundException,
    NotFoundException,
    ShoppingItemNotFoundException,
    UnAuthorizedException,
    UserNotFoundException,
)
from core.exception.openapi import create_error_response
from domains.group.schemas import (
    CreateGroupRequest,
    GroupInviteResponse,
    GroupResponse,
    InviteByNicknameRequest,
    JoinByCodeRequest,
    MergeRequest,
    MergeResponse,
    UpdateGroupRequest,
)
from domains.group.service import GroupService
from domains.ingredient.schemas import (
    AddIngredientRequest,
    AddIngredientResponse,
    GetIngredientResponse,
    UpdateIngredientRequest,
)
from domains.shopping.schemas import (
    AddShoppingItemsRequest,
    ShoppingItemResponse,
    UpdateShoppingItemRequest,
)

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=GroupResponse,
    responses=create_error_response(
        UnAuthorizedException, BadRequestException, ConflictException
    ),
)
async def create_group(
    request: CreateGroupRequest,
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    return await service.create(request)


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=GroupResponse,
    responses=create_error_response(UnAuthorizedException, NotFoundException),
)
async def get_my_group(
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    return await service.get_me()


@router.patch(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=GroupResponse,
    responses=create_error_response(
        UnAuthorizedException, ForbiddenException, NotFoundException, BadRequestException
    ),
)
async def update_my_group(
    request: UpdateGroupRequest,
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    return await service.update_me(request)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(
        UnAuthorizedException, ForbiddenException, NotFoundException
    ),
)
async def dissolve_group(
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.dissolve()


@router.post(
    "/me/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(
        UnAuthorizedException, BadRequestException, NotFoundException
    ),
)
async def leave_group(
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.leave()


@router.delete(
    "/me/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(
        UnAuthorizedException,
        ForbiddenException,
        BadRequestException,
        NotFoundException,
    ),
)
async def kick_member(
    user_id: UUID,
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.kick(user_id)


@router.post(
    "/me/invites",
    status_code=status.HTTP_201_CREATED,
    response_model=GroupInviteResponse,
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        NotFoundException,
        UserNotFoundException,
    ),
)
async def invite_by_nickname(
    request: InviteByNicknameRequest,
    service: GroupService = Depends(get_group_service),
) -> GroupInviteResponse:
    return await service.invite_by_nickname(request)


@router.get(
    "/invites",
    status_code=status.HTTP_200_OK,
    response_model=list[GroupInviteResponse],
    responses=create_error_response(UnAuthorizedException),
)
async def list_my_invites(
    service: GroupService = Depends(get_group_service),
) -> list[GroupInviteResponse]:
    return await service.list_my_invites()


@router.post(
    "/invites/{invite_id}/accept",
    status_code=status.HTTP_200_OK,
    response_model=GroupResponse,
    responses=create_error_response(
        UnAuthorizedException, ConflictException, NotFoundException
    ),
)
async def accept_invite(
    invite_id: UUID,
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    return await service.accept_invite(invite_id)


@router.post(
    "/invites/{invite_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(UnAuthorizedException, NotFoundException),
)
async def reject_invite(
    invite_id: UUID,
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.reject_invite(invite_id)


@router.post(
    "/join",
    status_code=status.HTTP_200_OK,
    response_model=GroupResponse,
    responses=create_error_response(
        UnAuthorizedException, ConflictException, NotFoundException
    ),
)
async def join_by_code(
    request: JoinByCodeRequest,
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    return await service.join_by_code(request)


@router.post(
    "/me/rotate-code",
    status_code=status.HTTP_200_OK,
    response_model=GroupResponse,
    responses=create_error_response(
        UnAuthorizedException, ForbiddenException, NotFoundException
    ),
)
async def rotate_invite_code(
    service: GroupService = Depends(get_group_service),
) -> GroupResponse:
    return await service.rotate_code()


@router.get(
    "/me/ingredients",
    status_code=status.HTTP_200_OK,
    response_model=list[GetIngredientResponse],
    responses=create_error_response(UnAuthorizedException, NotFoundException),
)
async def list_group_ingredients(
    service: GroupService = Depends(get_group_service),
) -> list[GetIngredientResponse]:
    return await service.list_ingredients()


@router.post(
    "/me/ingredients",
    status_code=status.HTTP_201_CREATED,
    response_model=list[AddIngredientResponse],
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        ConflictException,
        NotFoundException,
    ),
)
async def add_group_ingredients(
    request: AddIngredientRequest,
    service: GroupService = Depends(get_group_service),
) -> list[AddIngredientResponse]:
    return await service.add_ingredients(request)


@router.delete(
    "/me/ingredients",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(
        UnAuthorizedException, IngredientNotFoundException, NotFoundException
    ),
)
async def delete_all_group_ingredients(
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.delete_all_ingredients()


@router.patch(
    "/me/ingredients/{ingredient_id}",
    status_code=status.HTTP_200_OK,
    response_model=GetIngredientResponse,
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        IngredientNotFoundException,
        NotFoundException,
    ),
)
async def update_group_ingredient(
    ingredient_id: int,
    request: UpdateIngredientRequest,
    service: GroupService = Depends(get_group_service),
) -> GetIngredientResponse:
    return await service.update_ingredient(ingredient_id, request)


@router.delete(
    "/me/ingredients/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(
        UnAuthorizedException, IngredientNotFoundException, NotFoundException
    ),
)
async def delete_group_ingredient(
    ingredient_id: int,
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.delete_ingredient(ingredient_id)


@router.get(
    "/me/shopping-items",
    status_code=status.HTTP_200_OK,
    response_model=list[ShoppingItemResponse],
    responses=create_error_response(UnAuthorizedException, NotFoundException),
)
async def list_group_shopping_items(
    service: GroupService = Depends(get_group_service),
) -> list[ShoppingItemResponse]:
    return await service.list_shopping_items()


@router.post(
    "/me/shopping-items",
    status_code=status.HTTP_201_CREATED,
    response_model=list[ShoppingItemResponse],
    responses=create_error_response(
        UnAuthorizedException, BadRequestException, NotFoundException
    ),
)
async def add_group_shopping_items(
    request: AddShoppingItemsRequest,
    service: GroupService = Depends(get_group_service),
) -> list[ShoppingItemResponse]:
    return await service.add_shopping_items(request)


@router.delete(
    "/me/shopping-items",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(
        UnAuthorizedException, ShoppingItemNotFoundException, NotFoundException
    ),
)
async def delete_all_group_shopping_items(
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.delete_all_shopping_items()


@router.patch(
    "/me/shopping-items/{item_id}",
    status_code=status.HTTP_200_OK,
    response_model=ShoppingItemResponse,
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        ShoppingItemNotFoundException,
        NotFoundException,
    ),
)
async def update_group_shopping_item(
    item_id: int,
    request: UpdateShoppingItemRequest,
    service: GroupService = Depends(get_group_service),
) -> ShoppingItemResponse:
    return await service.update_shopping_item(item_id, request)


@router.delete(
    "/me/shopping-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(
        UnAuthorizedException, ShoppingItemNotFoundException, NotFoundException
    ),
)
async def delete_group_shopping_item(
    item_id: int,
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.delete_shopping_item(item_id)


@router.post(
    "/me/shopping-items/{item_id}/to-ingredient",
    status_code=status.HTTP_201_CREATED,
    response_model=AddIngredientResponse,
    responses=create_error_response(
        UnAuthorizedException,
        ConflictException,
        ShoppingItemNotFoundException,
        NotFoundException,
    ),
)
async def group_shopping_to_ingredient(
    item_id: int,
    service: GroupService = Depends(get_group_service),
) -> AddIngredientResponse:
    return await service.shopping_to_ingredient(item_id)


@router.post(
    "/me/merge",
    status_code=status.HTTP_200_OK,
    response_model=MergeResponse,
    responses=create_error_response(
        UnAuthorizedException, NotFoundException, BadRequestException
    ),
)
async def merge_personal_into_group(
    request: MergeRequest,
    service: GroupService = Depends(get_group_service),
) -> MergeResponse:
    return await service.merge(request)
