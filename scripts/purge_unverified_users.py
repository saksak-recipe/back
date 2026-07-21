"""오래된 미인증 사용자를 물리 삭제한다.

Usage (repo root, PYTHONPATH=src):
  uv run python scripts/purge_unverified_users.py --older-than-hours 24
  uv run python scripts/purge_unverified_users.py --older-than-hours 24 --dry-run
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.database import async_session_factory
from domains.group.model import Group, GroupInvite, GroupMember  # noqa: F401
from domains.ingredient.model import Ingredient  # noqa: F401
from domains.saved_recipe.model import SavedRecipe  # noqa: F401
from domains.shopping.model import ShoppingItem  # noqa: F401
from domains.user.repository import UserRepository
from domains.user.service import UserService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--older-than-hours",
        type=int,
        default=24,
        help="해당 시간보다 오래된 미인증 계정만 삭제합니다. (기본값: 24)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="삭제하지 않고 대상 개수만 출력합니다.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.older_than_hours < 0:
        raise ValueError("--older-than-hours 는 0 이상이어야 합니다.")

    older_than = timedelta(hours=args.older_than_hours)

    async with async_session_factory() as session:
        repo = UserRepository(session)
        service = UserService(repo)

        if args.dry_run:
            now = datetime.now(timezone.utc)
            candidates = await repo.list_unverified_before(now - older_than)
            print(
                f"[dry-run] would purge {len(candidates)} unverified user(s) "
                f"older than {args.older_than_hours}h"
            )
            return

        count = await service.purge_unverified_users(older_than=older_than)
        await session.commit()
        print(
            f"purged {count} unverified user(s) "
            f"older than {args.older_than_hours}h"
        )


if __name__ == "__main__":
    asyncio.run(main())
