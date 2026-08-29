"""Auth router — register, login, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from core.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
_service: AuthService | None = None


def get_service() -> AuthService:
    from api.routers.chat import get_store

    global _service
    if _service is None:
        _service = AuthService(get_store())
    return _service


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        return get_service().decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=120)
    email: str
    password: str = Field(min_length=8)
    plan: str = "free"


class UserResponse(BaseModel):
    email: str
    tenant_id: str
    role: str


@router.post("/register", response_model=UserResponse, status_code=201)
def register(req: RegisterRequest) -> dict:
    try:
        user = get_service().register_tenant(
            req.tenant_name, req.email, req.password, req.plan
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {k: user[k] for k in ("email", "tenant_id", "role")}


@router.post("/token")
def token(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    try:
        user = get_service().authenticate(form.username, form.password)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None
    return {"access_token": get_service().create_token(user["email"]), "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)) -> dict:
    return {"email": user["sub"], "tenant_id": user["tenant_id"], "role": user["role"]}


@router.post("/users", response_model=UserResponse, status_code=201)
def add_user(
    email: str,
    password: str,
    role: str = "member",
    admin: dict = Depends(require_admin),
) -> dict:
    try:
        user = get_service().add_user(admin["tenant_id"], email, password, role)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="Tenant not found") from None
    return {k: user[k] for k in ("email", "tenant_id", "role")}
