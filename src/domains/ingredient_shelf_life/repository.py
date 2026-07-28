from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.exceptions import DatabaseException
from domains.ingredient_matching import canonical_of
from domains.ingredient_matching.synonyms import SYNONYM_GROUPS
from domains.ingredient_shelf_life.model import (
    IngredientShelfLife,
    IngredientShelfLifeLog,
)


def _lookup_name_variants(name: str) -> set[str]:
    """Expand a name to DB lookup candidates via synonym canonical aliases."""
    variants: set[str] = {name}
    c = canonical_of(name)
    if c:
        variants.add(c)
    for canon, aliases in SYNONYM_GROUPS.items():
        if canonical_of(canon) != c:
            continue
        variants.add(canon)
        variants.update(aliases)
    return {v for v in variants if v}


class IngredientShelfLifeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_names(
        self, names: list[str]
    ) -> dict[str, IngredientShelfLife]:
        if not names:
            return {}
        try:
            unique_names = list(dict.fromkeys(names))
            query_names: set[str] = set()
            for name in unique_names:
                query_names.update(_lookup_name_variants(name))

            stmt = select(IngredientShelfLife).where(
                IngredientShelfLife.ingredient_name.in_(list(query_names))
            )
            result = await self.session.execute(stmt)
            rows = list(result.scalars().all())

            by_canonical: dict[str, IngredientShelfLife] = {}
            by_exact: dict[str, IngredientShelfLife] = {}
            for row in rows:
                by_exact[row.ingredient_name] = row
                by_canonical[canonical_of(row.ingredient_name)] = row

            mapped: dict[str, IngredientShelfLife] = {}
            for name in unique_names:
                row = by_exact.get(name) or by_canonical.get(canonical_of(name))
                if row is not None:
                    mapped[name] = row
            return mapped
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 보관일수 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def add_logs(self, logs: list[IngredientShelfLifeLog]) -> None:
        if not logs:
            return
        try:
            self.session.add_all(logs)
            await self.session.flush()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="식재료 보관일수 로그 저장 중 DB 오류가 발생했습니다."
            ) from e
