from __future__ import annotations

from datetime import date, timedelta

from core.exception.exceptions import BadRequestException
from domains.ingredient.model import Ingredient
from domains.ingredient.schemas import (
    AddIngredientResponse,
    GetIngredientResponse,
    IngredientStatus,
)

SOON_WITHIN_DAYS = 3

_STATUS_RANK: dict[IngredientStatus, int] = {
    "expired": 0,
    "soon": 1,
    "ok": 2,
    "unknown": 3,
}


def ensure_expiration_valid(purchase_date: date, expiration_date: date | None) -> None:
    if expiration_date is not None and expiration_date < purchase_date:
        raise BadRequestException(detail="유통기한은 구매일 이후여야 합니다.")


def compute_status(
    expiration_date: date | None, today: date | None = None
) -> IngredientStatus:
    today = today or date.today()
    if expiration_date is None:
        return "unknown"
    if expiration_date < today:
        return "expired"
    if expiration_date <= today + timedelta(days=SOON_WITHIN_DAYS):
        return "soon"
    return "ok"


def to_get_response(
    ingredient: Ingredient, today: date | None = None
) -> GetIngredientResponse:
    today = today or date.today()
    return GetIngredientResponse(
        id=ingredient.id,
        ingredient_name=ingredient.ingredient_name,
        purchase_date=ingredient.purchase_date,
        expiration_date=ingredient.expiration_date,
        status=compute_status(ingredient.expiration_date, today),
    )


def to_add_response(
    ingredient: Ingredient, today: date | None = None
) -> AddIngredientResponse:
    today = today or date.today()
    return AddIngredientResponse(
        id=ingredient.id,
        ingredient_name=ingredient.ingredient_name,
        purchase_date=ingredient.purchase_date,
        expiration_date=ingredient.expiration_date,
        status=compute_status(ingredient.expiration_date, today),
    )


def list_sort_key(ingredient: Ingredient, today: date) -> tuple:
    status = compute_status(ingredient.expiration_date, today)
    rank = _STATUS_RANK[status]
    if status == "unknown":
        created = ingredient.created_at
        ts = created.timestamp() if created is not None else 0.0
        return (rank, -ts)
    assert ingredient.expiration_date is not None
    return (rank, ingredient.expiration_date.toordinal())
