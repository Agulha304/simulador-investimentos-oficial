from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


PASSWORD_MIN, PASSWORD_MAX = 8, 72   # 72 = limite do bcrypt; MESMA regra no cadastro e na redefinição


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    created_at: datetime


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class MessageResponse(BaseModel):
    message: str
