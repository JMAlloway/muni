from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.security import hash_password as _hash_password, verify_password as _verify_password
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
import datetime as dt

from app.core.settings import settings
from app.core.db import get_session
from app.domain.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def create_admin_if_missing(db: AsyncSession):
    """Ensure a default admin user exists based on .env settings."""
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return
    # Check if admin already exists
    res = await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
    existing = res.scalar_one_or_none()
    if existing:
        return
    u = User(
        email=settings.ADMIN_EMAIL,
        password_hash=_hash_password(settings.ADMIN_PASSWORD),
        is_admin=True,
    )
    db.add(u)
    await db.commit()


def create_token(user_id: str, email: str) -> str:
    """Create a short-lived JWT access token."""
    now = dt.datetime.utcnow()
    payload = {
        "sub": user_id,
        "email": email,
        "exp": now + dt.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRES_MIN),
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def get_current_user(
    db: AsyncSession = Depends(get_session), token: str = Depends(oauth2_scheme)
) -> User:
    """Resolve and return the currently authenticated user from the JWT."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    user_id = payload.get("sub")
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Guard that only allows admin users."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# Helpers for signup/login flows
async def hash_password(pw: str) -> str:
    return _hash_password(pw)


async def verify_password(pw: str, hashed: str) -> bool:
    return _verify_password(pw, hashed)


