from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.redis import get_redis
from core.security import REFRESH_TOKEN_EXPIRE_SECONDS, get_access_token
from domains.auth.refresh_store import RefreshTokenStore
from domains.ai_recipe.agent import AiRecipeAgent
from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.service import AiRecipeService
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.service import IngredientService

from domains.user.repository import UserRepository
from domains.user.service import UserService
from domains.user.model import User
from domains.auth.service import AuthService
from domains.rag.retriever import RecipeRetriever, get_recipe_retriever
from domains.rag.service import RagService
from domains.recipe_detail.cache import RecipeDetailCache
from domains.recipe_detail.crawler import RecipeCrawler
from domains.recipe_detail.service import RecipeDetailService
from domains.saved_recipe.repository import SavedRecipeRepository
from domains.saved_recipe.service import SavedRecipeService


_recipe_crawler = RecipeCrawler()


def get_user_repo(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_user_service(user_repo: UserRepository = Depends(get_user_repo)) -> UserService:
    return UserService(user_repo=user_repo)


def get_refresh_store() -> RefreshTokenStore:
    return RefreshTokenStore(get_redis(), ttl_seconds=REFRESH_TOKEN_EXPIRE_SECONDS)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repo),
    refresh_store: RefreshTokenStore = Depends(get_refresh_store),
) -> AuthService:
    return AuthService(user_repo=user_repo, refresh_store=refresh_store)


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
    return IngredientService(
        user=user,
        ingredient_repo=ingredient_repo,
        list_cache=AiRecipeCache(get_redis()),
    )


def get_ai_recipe_service(
    user: User = Depends(get_current_user),
    ingredient_repo: IngredientRepository = Depends(get_ingredient_repo),
) -> AiRecipeService:
    cache = AiRecipeCache(get_redis(), ttl_seconds=86400)
    return AiRecipeService(
        user=user,
        ingredient_repo=ingredient_repo,
        agent=AiRecipeAgent(),
        cache=cache,
    )


def get_rag_retriever() -> RecipeRetriever:
    return get_recipe_retriever()


def get_rag_service(
    user: User = Depends(get_current_user),
    ingredient_repo: IngredientRepository = Depends(get_ingredient_repo),
    retriever: RecipeRetriever = Depends(get_rag_retriever),
) -> RagService:
    return RagService(
        user=user,
        ingredient_repo=ingredient_repo,
        retriever=retriever,
    )


def get_recipe_detail_service(
    user: User = Depends(get_current_user),
) -> RecipeDetailService:
    cache = RecipeDetailCache(get_redis(), ttl_seconds=86400)
    return RecipeDetailService(crawler=_recipe_crawler, cache=cache)


def get_saved_recipe_repo(
    session: AsyncSession = Depends(get_db),
) -> SavedRecipeRepository:
    return SavedRecipeRepository(session)


def get_saved_recipe_service(
    user: User = Depends(get_current_user),
    repo: SavedRecipeRepository = Depends(get_saved_recipe_repo),
    ai_recipe_service: AiRecipeService = Depends(get_ai_recipe_service),
    recipe_detail_service: RecipeDetailService = Depends(get_recipe_detail_service),
) -> SavedRecipeService:
    return SavedRecipeService(
        user=user,
        repo=repo,
        ai_recipe_service=ai_recipe_service,
        recipe_detail_service=recipe_detail_service,
    )
