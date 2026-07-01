from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

load_dotenv()

#import from .env import DATABASE_URL
import os
Database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:Admin%40123%24@10.160.0.6:5432/observability")

engine = create_async_engine(
    Database_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session