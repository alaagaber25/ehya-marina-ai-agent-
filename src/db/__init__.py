import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import config as config

from .chat import Chat, Message  # noqa: F401
from .service import DatabaseService, MessageDirection  # noqa: F401

logger = logging.getLogger(__name__)

# Real or mock engine and sessionmaker
try:
    engine = create_async_engine(config.DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    using_mock = False

except Exception:
    logger.error("NO DATABASE CONNECTION — using mocks")
    using_mock = True

    # Create a fake session
    fake_session = AsyncMock(spec=AsyncSession)

    # You can mock execute/scalars behavior as you like, e.g. default empty:
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = []
    fake_session.execute.return_value = fake_result
    fake_session.scalars = fake_session.execute  # alias if you call .scalars directly

    # Mock engine whose .begin() yields fake_session
    fake_engine = MagicMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = fake_session
    cm.__aexit__.return_value = None
    fake_engine.begin.return_value = cm
    fake_engine.dispose = AsyncMock()

    engine = fake_engine

    @asynccontextmanager
    async def mock_session():
        yield fake_session

    AsyncSessionLocal = mock_session

# Dependency to get a session
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Create tables (or no‑op if mock)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
