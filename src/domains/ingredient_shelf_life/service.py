from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from domains.ingredient_shelf_life.model import IngredientShelfLifeLog
from domains.ingredient_shelf_life.repository import IngredientShelfLifeRepository


class IngredientShelfLifeService:
    def __init__(self, repo: IngredientShelfLifeRepository):
        self.repo = repo

    async def resolve_expirations_on_add(
        self,
        *,
        names: list[str],
        purchase_date: date,
        expiration_date: date | None,
        user_id: UUID | None,
    ) -> list[date | None]:
        """Resolve expiration dates for ingredients being added.

        - If ``expiration_date`` is None: autofill from master, or log ``missing``.
        - If set: keep user value; log ``deviation`` or ``missing_with_user_input``.
        """
        masters = await self.repo.get_by_names(names)
        resolved: list[date | None] = []
        logs: list[IngredientShelfLifeLog] = []

        for name in names:
            master = masters.get(name)
            if expiration_date is None:
                if master is not None:
                    resolved.append(
                        purchase_date + timedelta(days=master.shelf_life_days)
                    )
                else:
                    logs.append(
                        IngredientShelfLifeLog(
                            log_type="missing",
                            ingredient_name=name,
                            user_id=user_id,
                            purchase_date=purchase_date,
                            user_expiration_date=None,
                            user_shelf_life_days=None,
                            master_shelf_life_days=None,
                        )
                    )
                    resolved.append(None)
                continue

            user_days = (expiration_date - purchase_date).days
            if master is None:
                logs.append(
                    IngredientShelfLifeLog(
                        log_type="missing_with_user_input",
                        ingredient_name=name,
                        user_id=user_id,
                        purchase_date=purchase_date,
                        user_expiration_date=expiration_date,
                        user_shelf_life_days=user_days,
                        master_shelf_life_days=None,
                    )
                )
            elif master.shelf_life_days != user_days:
                logs.append(
                    IngredientShelfLifeLog(
                        log_type="deviation",
                        ingredient_name=name,
                        user_id=user_id,
                        purchase_date=purchase_date,
                        user_expiration_date=expiration_date,
                        user_shelf_life_days=user_days,
                        master_shelf_life_days=master.shelf_life_days,
                    )
                )
            resolved.append(expiration_date)

        await self.repo.add_logs(logs)
        return resolved
