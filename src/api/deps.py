from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_access_token
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.service import IngredientService

from domains.user.repository import UserRepository
from domains.user.service import UserService
from domains.user.model import User
from domains.auth.service import AuthService


def get_user_repo(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_user_service(user_repo: UserRepository = Depends(get_user_repo)) -> UserService:
    return UserService(user_repo=user_repo)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repo),
) -> AuthService:
    return AuthService(user_repo=user_repo)


async def get_current_user(
    access_token: str = Depends(get_access_token),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    return await auth_service.get_user_by_token(access_token)


def get_ingredient_repo(
    session: AsyncSession = Depends(get_db),
) -> IngredientRepository:
    return IngredientRepository(session)


def get_ingredient_service(
    user: User = Depends(get_current_user),
    ingredient_repo: IngredientRepository = Depends(get_ingredient_repo),
) -> IngredientService:
    return IngredientService(user=user, ingredient_repo=ingredient_repo)
