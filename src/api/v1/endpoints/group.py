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

router = APIRouter(prefix="/groups", tags=["그룹"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=GroupResponse,
    summary="그룹 생성",
    description="새 그룹을 생성하고 현재 사용자를 그룹장으로 등록합니다.",
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
    summary="내 그룹 조회",
    description="현재 사용자가 속한 그룹 정보를 조회합니다.",
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
    summary="내 그룹 수정",
    description="그룹 이름 등 내 그룹 정보를 수정합니다. 그룹장만 가능합니다.",
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
    summary="그룹 해체",
    description="내 그룹을 해체합니다. 그룹장만 가능합니다.",
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
    summary="그룹 나가기",
    description="현재 사용자가 속한 그룹에서 나갑니다.",
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
    summary="그룹 멤버 추방",
    description="그룹에서 특정 멤버를 추방합니다. 그룹장만 가능합니다.",
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
    summary="닉네임으로 초대",
    description="닉네임으로 사용자를 검색해 내 그룹에 초대합니다.",
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        ConflictException,
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
    summary="받은 초대 목록",
    description="현재 사용자에게 온 그룹 초대 목록을 조회합니다.",
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
    summary="초대 수락",
    description="받은 그룹 초대를 수락하고 해당 그룹에 가입합니다.",
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
    summary="초대 거절",
    description="받은 그룹 초대를 거절합니다.",
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
    summary="초대 코드로 가입",
    description="그룹 초대 코드로 그룹에 가입합니다.",
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
    summary="초대 코드 재발급",
    description="그룹 초대 코드를 새로 발급합니다. 그룹장만 가능합니다.",
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
    summary="그룹 재료 목록 조회",
    description="내 그룹 공유 냉장고의 재료 목록을 조회합니다.",
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
    summary="그룹 재료 추가",
    description="내 그룹 공유 냉장고에 재료를 추가합니다.",
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
    summary="그룹 재료 전체 삭제",
    description="내 그룹 공유 냉장고의 모든 재료를 삭제합니다.",
    responses=create_error_response(UnAuthorizedException, NotFoundException),
)
async def delete_all_group_ingredients(
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.delete_all_ingredients()


@router.patch(
    "/me/ingredients/{ingredient_id}",
    status_code=status.HTTP_200_OK,
    response_model=GetIngredientResponse,
    summary="그룹 재료 수정",
    description="내 그룹 공유 냉장고의 특정 재료를 수정합니다.",
    responses=create_error_response(
        UnAuthorizedException,
        BadRequestException,
        ConflictException,
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
    summary="그룹 재료 삭제",
    description="내 그룹 공유 냉장고의 특정 재료를 삭제합니다.",
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
    summary="그룹 장보기 목록 조회",
    description="내 그룹 공유 장보기 목록을 조회합니다.",
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
    summary="그룹 장보기 항목 추가",
    description="내 그룹 공유 장보기 목록에 항목을 추가합니다.",
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
    summary="그룹 장보기 전체 삭제",
    description="내 그룹 공유 장보기 목록의 모든 항목을 삭제합니다.",
    responses=create_error_response(UnAuthorizedException, NotFoundException),
)
async def delete_all_group_shopping_items(
    service: GroupService = Depends(get_group_service),
) -> None:
    await service.delete_all_shopping_items()


@router.patch(
    "/me/shopping-items/{item_id}",
    status_code=status.HTTP_200_OK,
    response_model=ShoppingItemResponse,
    summary="그룹 장보기 항목 수정",
    description="내 그룹 공유 장보기 목록의 특정 항목을 수정합니다.",
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
    summary="그룹 장보기 항목 삭제",
    description="내 그룹 공유 장보기 목록의 특정 항목을 삭제합니다.",
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
    summary="그룹 장보기 항목을 재료로 전환",
    description="그룹 장보기 항목을 그룹 냉장고 재료로 옮기고 해당 장보기 항목을 제거합니다.",
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
    summary="개인 데이터 그룹 병합",
    description="개인 냉장고·장보기 데이터를 그룹 공유 목록으로 병합합니다.",
    responses=create_error_response(
        UnAuthorizedException, NotFoundException, BadRequestException
    ),
)
async def merge_personal_into_group(
    request: MergeRequest,
    service: GroupService = Depends(get_group_service),
) -> MergeResponse:
    return await service.merge(request)
