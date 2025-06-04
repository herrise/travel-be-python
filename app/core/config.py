import secrets
from typing import List

class Settings:
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS settings
    CORS_ORIGINS: List[str] = ["*"]  # Configure for production
    
    # App settings
    APP_NAME: str = "JWT Authentication API"
    VERSION: str = "1.0.0"

settings = Settings()