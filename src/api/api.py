from fastapi import APIRouter

from api.v1.endpoints.auth import router as auth_router
from api.v1.endpoints.user import router as user_router
from api.v1.endpoints.ingredient import router as ingredient_router
from api.v1.endpoints.rag import router as rag_router
from api.v1.endpoints.saved_recipe import router as saved_recipe_router
from api.v1.endpoints.shopping import router as shopping_router
from api.v1.endpoints.group import router as group_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(ingredient_router)
api_router.include_router(rag_router)
api_router.include_router(saved_recipe_router)
api_router.include_router(shopping_router)
api_router.include_router(group_router)
