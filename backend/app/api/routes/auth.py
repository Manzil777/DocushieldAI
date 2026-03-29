from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.auth import RefreshTokenRequest, TokenResponse, UserCreate, UserLogin
from app.services.auth_service import (
    authenticate_user,
    create_tokens,
    get_current_user,
    get_db,
    register_user,
    revoke_refresh_token,
    store_refresh_token,
    verify_refresh_token,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(payload: UserCreate, db: Session = Depends(get_db)) -> dict[str, str]:
    register_user(db, payload.email, payload.password)
    return {"message": "User registered successfully"}


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    tokens = create_tokens(user.id)
    store_refresh_token(tokens["refresh_token"], user.id)
    return TokenResponse(**tokens)


@router.post("/refresh")
def refresh(payload: RefreshTokenRequest) -> dict[str, str]:
    user_id = verify_refresh_token(payload.refresh_token)
    access_token = create_tokens(user_id)["access_token"]
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(payload: RefreshTokenRequest) -> dict[str, str]:
    revoke_refresh_token(payload.refresh_token)
    return {"message": "Logged out successfully"}


@router.get("/me")
def me(current_user: str = Depends(get_current_user)) -> dict[str, str]:
    return {"user_id": current_user}
