from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"

# Request Models
class UserRegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenRefreshRequest(BaseModel):
    refresh_token: str

# Response Models
class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class LoginResponse(BaseModel):
    user: UserResponse
    tokens: TokenResponse

class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class MessageResponse(BaseModel):
    message: str

# Database Models
class User(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    password_hash: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]

class RefreshToken(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    is_revoked: bool
    created_at: datetime
    user_agent: Optional[str]
    ip_address: Optional[str]

class BlacklistedToken(BaseModel):
    id: uuid.UUID
    token_jti: str
    expires_at: datetime
    created_at: datetime

class UserSession(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    session_token: str
    expires_at: datetime
    created_at: datetime
    last_accessed: datetime
    user_agent: Optional[str]
    ip_address: Optional[str]
    is_active: bool

# Admin Models
class AdminUserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    per_page: int
    pages: int

class UserUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None

# User model for database
class UserInDB(BaseModel):
    id: int
    email: EmailStr
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password_hash: str
    role: str = "user"
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True  # For Pydantic v2