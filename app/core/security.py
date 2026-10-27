import asyncio
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
from app.core.config import settings

_bcrypt_semaphore = asyncio.Semaphore(4)


async def hash_password(password: str) -> str:
    async with _bcrypt_semaphore:
        def _hash() -> str:
            salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
            return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
        return await asyncio.to_thread(_hash)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    async with _bcrypt_semaphore:
        def _verify() -> bool:
            try:
                return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
            except Exception:
                return False
        return await asyncio.to_thread(_verify)


def crear_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def verificar_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        return None
