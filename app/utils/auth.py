import os
import jwt
import bcrypt
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
import uuid
from app.models.user import UserResponse, UserInDB
from passlib.context import CryptContext
import logging
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
import hashlib


load_dotenv()

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-jwt-key-change-this-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

security = HTTPBearer()

class AuthUtils:

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({
            "exp": expire,
            "type": "access",
            "jti": str(uuid.uuid4())  # JWT ID for token blacklisting
        })
        
        # Ensure proper string encoding
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        # PyJWT 2.0+ returns string directly, but ensure it's a string
        if isinstance(encoded_jwt, bytes):
            encoded_jwt = encoded_jwt.decode('utf-8')
        
        return encoded_jwt

    @staticmethod
    def create_refresh_token(data: dict) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        to_encode.update({
            "exp": expire,
            "type": "refresh",
            "jti": str(uuid.uuid4())
        })
        
        # Ensure proper string encoding
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        # PyJWT 2.0+ returns string directly, but ensure it's a string
        if isinstance(encoded_jwt, bytes):
            encoded_jwt = encoded_jwt.decode('utf-8')
        
        return encoded_jwt

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)

    @staticmethod
    def generate_reset_token() -> str:
        """Generate a secure reset token"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_verification_token() -> str:
        """Generate a secure verification token"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token for secure storage"""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def get_token_expiry_time() -> datetime:
        """Get refresh token expiry time"""
        return datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    @staticmethod
    def extract_user_agent_and_ip(request: Request) -> Tuple[str, str]:
        """Extract user agent and IP address from request"""
        user_agent = request.headers.get("user-agent", "Unknown")
        # Get real IP considering proxy headers
        ip_address = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.headers.get("x-real-ip", "") or
            request.client.host if request.client else "Unknown"
        )
        return user_agent, ip_address

    @staticmethod
    def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate JWT access token"""
        try:
            # Ensure token is a string and strip whitespace
            if not isinstance(token, str):
                logging.error(f"Token is not a string: {type(token)}")
                return None
            
            token = token.strip()
            
            # Basic token format validation
            if not token or len(token.split('.')) != 3:
                logging.error("Invalid token format")
                return None
            
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            logging.info(f"Token decoded successfully. Payload: {payload}")
            
            if payload.get("type") != "access":
                logging.warning(f"Invalid token type: {payload.get('type')}")
                return None
            return payload
            
        except ExpiredSignatureError:
            logging.warning("Token has expired")
            return None
        except InvalidTokenError as e:
            logging.warning(f"JWT decode error: {e}")
            return None
        except UnicodeDecodeError as e:
            logging.error(f"Token encoding error: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error decoding token: {e}")
            return None


# Optional authentication (for routes that work with or without auth)
async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[Dict[str, Any]]:
    """Get current user optionally (returns None if no valid token)"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None

# Dependency functions
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    from app.databases.service import DatabaseService
    from app.models.user import UserResponse

    token = credentials.credentials
    logging.info(f"Attempting to authenticate with token: {token[:20]}...")

    try:
        payload = AuthUtils.decode_access_token(token)
        if not payload:
            logging.warning("Failed to decode token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        jti = payload.get("jti")
        logging.info(f"Token JTI: {jti}")
        
        if jti:
            is_blacklisted = await DatabaseService.is_token_blacklisted(jti)
            logging.info(f"Token blacklisted: {is_blacklisted}")
            if is_blacklisted:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        
        # Get user ID from token
        user_id = payload.get("sub")
        logging.info(f"User ID from token: {user_id}")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user from database
        user = await DatabaseService.get_user_by_id(user_id)
        logging.info(f"User found in database: {user is not None}")
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logging.info(f"User details: ID={user.id}, Email={user.email}, Role={user.role}, Active={user.is_active}")
        
        # Convert UserInDB to UserResponse
        user_response = UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login=user.last_login
        )
        
        logging.info("Authentication successful")
        return user_response
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_active_user(current_user = Depends(get_current_user)):
    """Get current active user"""
    logging.info(f"Checking if user is active: {current_user.is_active}")
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


async def require_admin(current_user = Depends(get_current_active_user)):
    """Require admin role"""
    logging.info(f"Checking admin role. User role: {current_user.role}")
    if current_user.role != "admin":
        logging.warning(f"Access denied. Required: admin, Got: {current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    logging.info("Admin access granted")
    return current_user