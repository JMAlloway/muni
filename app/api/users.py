from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_session
from app.domain.models import User
from app.schemas import UserCreate, UserOut, TokenOut
from app.auth import create_token, hash_password, verify_password
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=UserOut)
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_session)):
    exists = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")
    u = User(email=payload.email, password_hash=await hash_password(payload.password))
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return UserOut(id=u.id, email=u.email, is_admin=u.is_admin)

@router.post("/login", response_model=TokenOut)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_session)):
    user = (await db.execute(select(User).where(User.email == form.username))).scalar_one_or_none()
    if not user or not await verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    return TokenOut(access_token=create_token(user.id, user.email))
