"""
ReconMind Backend — database/db.py
Async PostgreSQL connection using SQLAlchemy + asyncpg.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────
# Engine
# ─────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,       # SQL query logging in dev
    pool_pre_ping=True,        # Check connection before use
    pool_size=10,
    max_overflow=20,
)

# ─────────────────────────────────────────
# Session Factory
# ─────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ─────────────────────────────────────────
# Base Model
# ─────────────────────────────────────────
class Base(DeclarativeBase):
    pass

# ─────────────────────────────────────────
# Initialize DB (create tables)
# ─────────────────────────────────────────
async def init_db():
    """Create all tables on startup if they don't exist."""
    # Import models so Base knows about them
    from database import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("All database tables created/verified.")

# ─────────────────────────────────────────
# Dependency — get DB session
# ─────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency. Provides a database session per request.
    
    Usage in routes:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
