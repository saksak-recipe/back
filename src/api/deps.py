from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from core.redis import get_redis
from core.security import REFRESH_TOKEN_EXPIRE_SECONDS, get_access_token
from domains.auth.email_service import EmailService
from domains.auth.refresh_store import RefreshTokenStore
from domains.auth.verification_store import VerificationCodeStore
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
from domains.group.repository import GroupRepository
from domains.group.service import GroupService
from domains.shopping.repository import ShoppingRepository
from domains.shopping.service import ShoppingService


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
    return AuthService(
        user_repo=user_repo,
        refresh_store=refresh_store,
        verification_store=VerificationCodeStore(get_redis()),
        email_service=EmailService(
            backend=settings.EMAIL_BACKEND,
            smtp_host=settings.SMTP_HOST,
            smtp_port=settings.SMTP_PORT,
            smtp_user=settings.SMTP_USER,
            smtp_password=(
                settings.SMTP_PASSWORD.get_secret_value()
                if settings.SMTP_PASSWORD is not None
                else None
            ),
            smtp_from_email=settings.SMTP_FROM_EMAIL,
            smtp_from_name=settings.SMTP_FROM_NAME,
            smtp_use_tls=settings.SMTP_USE_TLS,
        ),
    )


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


def get_shopping_repo(
    session: AsyncSession = Depends(get_db),
) -> ShoppingRepository:
    return ShoppingRepository(session)


def get_shopping_service(
    user: User = Depends(get_current_user),
    shopping_repo: ShoppingRepository = Depends(get_shopping_repo),
    ingredient_repo: IngredientRepository = Depends(get_ingredient_repo),
) -> ShoppingService:
    return ShoppingService(
        user=user,
        shopping_repo=shopping_repo,
        ingredient_repo=ingredient_repo,
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


def get_group_service(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GroupService:
    return GroupService(
        user=user,
        group_repo=GroupRepository(session),
        user_repo=UserRepository(session),
        ingredient_repo=IngredientRepository(session),
        shopping_repo=ShoppingRepository(session),
    )
