import secrets
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.dependencies import exigir_password_al_dia
from app.core.errors import registrar_manejadores
from app.core.security import hash_password
from app.modules.clientes.router import propios_router as clientes_propios_router
from app.modules.clientes.router import router as clientes_router
from app.modules.clientes.router import vehiculos_router
from app.modules.health.router import router as health_router
from app.modules.repuestos.router import router as repuestos_router
from app.modules.usuarios.auth_router import router as auth_router
from app.modules.usuarios.router import eventos_router
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

# --- Dos grupos de rutas (DD-05 / US-015 CA-1) ------------------------------
# El control de ``debe_cambiar_password`` se monta **una sola vez**, como
# dependencia del grupo protegido: FastAPI suma dependencias y no las resta, así
# que montarlo por router no alcanzaría ni se podría «sacar» en una ruta. El
# grupo abierto no lo lleva: el afectado tiene que poder loguearse, consultar
# ``/auth/yo`` y cambiar la contraseña (RN-06).
grupo_abierto = APIRouter()
grupo_protegido = APIRouter(dependencies=[Depends(exigir_password_al_dia)])

# Abierto: ``/health`` y ``/auth``. ``/auth/yo`` y ``/auth/cambiar-password``
# exigen sesión por dentro (``get_usuario_actual``), pero no el cambio
# obligatorio: si lo exigieran, un usuario con clave provisoria no podría
# cambiar la clave nunca.
grupo_abierto.include_router(health_router)
grupo_abierto.include_router(auth_router)

# Protegido: todo lo demás. El 401 lo aporta ``get_usuario_actual`` (vía la
# dependencia del grupo), el 403 del cambio pendiente el grupo, y el permiso por
# rol ``requiere_rol`` en cada ruta, consultando la base en cada petición
# (RN-04). Los routers conservan su prefix y sus tags.
grupo_protegido.include_router(usuarios_router)
grupo_protegido.include_router(eventos_router)
grupo_protegido.include_router(repuestos_router)
grupo_protegido.include_router(clientes_router)
grupo_protegido.include_router(vehiculos_router)
grupo_protegido.include_router(clientes_propios_router)

app.include_router(grupo_abierto)
app.include_router(grupo_protegido)


@app.get("/", status_code=200)
async def root() -> dict:
    return {"message": "API Taller Mecánico funcionando correctamente"}
