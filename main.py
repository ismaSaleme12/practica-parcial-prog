from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.modules.health.router import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El motor y la fábrica de sesiones se crean acá, nunca al importar el módulo.
    engine = create_async_engine(
        settings.ASYNC_DATABASE_URL,
        echo=settings.SQL_ECHO,
        pool_size=settings.POOL_SIZE,
        future=True,
    )
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    app.state.engine = engine
    app.state.session_maker = session_maker

    yield

    await engine.dispose()


app = FastAPI(
    title="API Taller Mecánico",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router)


@app.get("/", status_code=200)
async def root() -> dict:
    return {"message": "API Taller Mecánico funcionando correctamente"}
