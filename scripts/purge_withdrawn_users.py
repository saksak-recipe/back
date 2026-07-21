"""유예 기간이 지난 soft-deleted 사용자를 물리 삭제한다.

Usage (repo root, PYTHONPATH=src):
  uv run python scripts/purge_withdrawn_users.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.database import async_session_factory
from domains.user.repository import UserRepository
from domains.user.service import UserService


async def main() -> None:
    async with async_session_factory() as session:
        service = UserService(UserRepository(session))
        count = await service.purge_expired_withdrawn_users()
        await session.commit()
        print(f"purged {count} user(s)")


if __name__ == "__main__":
    asyncio.run(main())
