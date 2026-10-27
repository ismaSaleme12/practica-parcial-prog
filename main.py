import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.errors import registrar_manejadores
from app.core.security import hash_password
from app.modules.health.router import router as health_router
from app.modules.repuestos.router import router as repuestos_router
from app.modules.usuarios.auth_router import router as auth_router
from app.modules.usuarios.router import router as usuarios_router

# Registro central de modelos: sin este import, las relaciones que cruzan módulos
# no se resuelven («expression 'ItemOrden' failed to locate a name»). Se importa
# el registro y no un módulo suelto (regla dura).
import app.models  # noqa: E402,F401  # isort: skip


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

    # Hash ficticio del login (RN-09): se calcula UNA vez, con el costo de la
    # configuración. Cuando el correo no existe, el login verifica contra este
    # hash para responder igual y tardar parecido, sin revelar qué cuentas hay.
    app.state.hash_ficticio = await hash_password(secrets.token_urlsafe(32))

    yield

    await engine.dispose()


app = FastAPI(
    title="API Taller Mecánico",
    version="1.0.0",
    lifespan=lifespan,
)

# Traducción central de errores (RN-18): IntegrityError → 409, validación → 422.
# Se registra antes de montar los routers para que cubra todos los endpoints.
registrar_manejadores(app)

app.include_router(health_router)

# Autenticación (C-07): router propio del módulo `usuarios`, con prefix `/auth`.
# Va en el grupo abierto: registro y login no exigen cookie, y `/auth/yo` y el
# cambio de contraseña la exigen por dentro (`get_usuario_actual`). C-08 lo
# re-monta junto con `health` en el grupo abierto y mueve `usuarios`/`repuestos`
# al grupo protegido, con el control de `debe_cambiar_password` montado una vez
# (DD-05 / US-015 CA-1).
app.include_router(auth_router)

# Routers de prototipo de C-06 (contratos y errores). Todavía en abierto porque
# C-08 aún no existe: C-08 los re-monta en el grupo protegido y agrega
# requiere_rol. Hasta entonces POST /usuarios y POST /repuestos son públicos.
app.include_router(usuarios_router)
app.include_router(repuestos_router)


@app.get("/", status_code=200)
async def root() -> dict:
    return {"message": "API Taller Mecánico funcionando correctamente"}
