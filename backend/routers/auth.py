from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from backend.core.security import create_access_token
from backend.dependencies import CurrentUser, DbSession
from backend.schemas.auth import (
    ForgotPasswordRequest, LoginRequest, MessageResponse, RegisterRequest, ResetPasswordRequest, TokenResponse, UserOut,
)
from backend.services import auth_service, mailer

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession):
    try:
        user = auth_service.register_user(db, email=body.email, name=body.name, password=body.password)
    except auth_service.EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado") from None
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: DbSession):
    user = auth_service.authenticate(db, body.email, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


FORGOT_MESSAGE = "Se o e-mail existir, enviaremos um link para redefinir a senha."


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:                                   # atrás do proxy do Render/Cloudflare
        return fwd.split(",")[0].strip()[:64] or None
    return request.client.host if request.client else None


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(body: ForgotPasswordRequest, request: Request, background: BackgroundTasks, db: DbSession):
    """Resposta SEMPRE igual (200 + mensagem genérica), exista a conta ou não. O e-mail sai em background."""
    try:
        result = auth_service.request_password_reset(db, body.email, _client_ip(request))
    except auth_service.ResetRateLimitedIPError:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Tente novamente mais tarde.") from None
    if result:
        user, token = result
        background.add_task(mailer.send_password_reset_safe, user.email, user.name, token)
    return MessageResponse(message=FORGOT_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, db: DbSession):
    try:
        auth_service.reset_password(db, body.token, body.new_password)
    except auth_service.InvalidResetTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Link inválido ou expirado. Peça um novo.") from None
    return MessageResponse(message="Senha redefinida com sucesso. Faça login com a nova senha.")
