from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SetupStatus(BaseModel):
    needs_initial_admin: bool


class InitialAdminIn(BaseModel):
    setup_token: str
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str
    password_confirm: str


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    role: str


class LoginOut(BaseModel):
    user: UserOut
    csrf_token: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str
