from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from typing import Dict, Any
import jwt
import uuid  # Add this import for JWT refresh token
import logging  # Add this import
from datetime import datetime, timezone, timedelta

from app.models.user import (
    UserRegisterRequest, UserLoginRequest, TokenRefreshRequest,
    UserResponse, LoginResponse, TokenResponse, RefreshTokenResponse,
    MessageResponse, AdminUserListResponse, UserUpdateRequest
)
from app.utils.auth import (
    AuthUtils, get_current_user, require_admin, security,
    ACCESS_TOKEN_EXPIRE_MINUTES, JWT_SECRET_KEY, JWT_ALGORITHM
)
from app.databases.service import DatabaseService

# Add logger configuration
logger = logging.getLogger(__name__)

router = APIRouter()

# Also add the missing constant
REFRESH_TOKEN_EXPIRE_DAYS = 30 

@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegisterRequest, request: Request):
    """Register a new user"""
    try:
        # Hash password
        password_hash = AuthUtils.hash_password(user_data.password)
        
        # Create user
        user = await DatabaseService.create_user(user_data, password_hash)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user"
            )
        
        # Create tokens
        access_token = AuthUtils.create_access_token({"sub": str(user.id)})
        refresh_token = AuthUtils.create_refresh_token()
        refresh_token_hash = AuthUtils.hash_token(refresh_token)
        
        # Get user agent and IP
        user_agent, ip_address = AuthUtils.extract_user_agent_and_ip(request)
        
        # Store refresh token
        expires_at = AuthUtils.get_token_expiry_time()
        await DatabaseService.create_refresh_token(
            str(user.id), refresh_token_hash, expires_at, user_agent, ip_address
        )
        
        # Update last login
        await DatabaseService.update_user_last_login(str(user.id))
        
        # Prepare response
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
        
        tokens = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
        return LoginResponse(user=user_response, tokens=tokens)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@router.post("/login", response_model=LoginResponse)
async def login(login_data: UserLoginRequest, request: Request):
    """User login"""
    # Get user by email
    user = await DatabaseService.get_user_by_email(login_data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled"
        )
    
    # Verify password
    if not AuthUtils.verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Create tokens - both need the user data
    token_data = {"sub": str(user.id)}
    access_token = AuthUtils.create_access_token(token_data)
    refresh_token = AuthUtils.create_refresh_token(token_data)  # Fixed: added token_data parameter
    refresh_token_hash = AuthUtils.hash_token(refresh_token)
    
    # Get user agent and IP
    user_agent, ip_address = AuthUtils.extract_user_agent_and_ip(request)
    
    # Store refresh token
    expires_at = AuthUtils.get_token_expiry_time()
    await DatabaseService.create_refresh_token(
        str(user.id), refresh_token_hash, expires_at, user_agent, ip_address
    )
    
    # Update last login
    await DatabaseService.update_user_last_login(str(user.id))
    
    # Prepare response
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
    
    tokens = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    return LoginResponse(user=user_response, tokens=tokens)

# This file contains an improved refresh token implementation
# Replace the refresh_token endpoint in routes/auth.py with this implementation

@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(token_data: TokenRefreshRequest, request: Request):
    """Refresh access token using refresh token"""
    try:
        refresh_token = token_data.refresh_token
        
        # Get user agent and IP for security
        user_agent, ip_address = AuthUtils.extract_user_agent_and_ip(request)
        
        # Find refresh token in database by trying to match hashes
        # This is a more secure approach than storing tokens in plain text
        
        # Get all non-revoked, non-expired refresh tokens
        from ..postgres import fetch
        query = """
            SELECT rt.id, rt.user_id, rt.token_hash, rt.expires_at, rt.created_at,
                   rt.user_agent, rt.ip_address,
                   u.id as user_id, u.email, u.username, u.role, u.is_active
            FROM refresh_tokens rt
            JOIN users u ON rt.user_id = u.id
            WHERE rt.is_revoked = false 
            AND rt.expires_at > $1
            ORDER BY rt.created_at DESC
        """
        
        records = await fetch(query, datetime.now(timezone.utc))
        
        # Check each token hash to find a match
        matched_token = None
        user_data = None
        
        for record in records:
            if AuthUtils.verify_token_hash(refresh_token, record['token_hash']):
                matched_token = record
                user_data = {
                    'id': record['user_id'],
                    'email': record['email'],
                    'username': record['username'],
                    'role': record['role'],
                    'is_active': record['is_active']
                }
                break
        
        if not matched_token or not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Check if user is still active
        if not user_data['is_active']:
            # Revoke the token and reject
            await DatabaseService.revoke_refresh_token(str(matched_token['id']))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled"
            )
        
        # Optional: Check if IP/User-Agent matches (for enhanced security)
        # Uncomment the following lines if you want strict IP/UA validation
        # if matched_token['ip_address'] != ip_address:
        #     await DatabaseService.revoke_refresh_token(str(matched_token['id']))
        #     raise HTTPException(
        #         status_code=status.HTTP_401_UNAUTHORIZED,
        #         detail="Token used from different location"
        #     )
        
        # Create new access token
        access_token = AuthUtils.create_access_token({"sub": str(user_data['id'])})
        
        # Optionally create a new refresh token (token rotation)
        # This is a security best practice
        new_refresh_token = AuthUtils.create_refresh_token()
        new_refresh_token_hash = AuthUtils.hash_token(new_refresh_token)
        
        # Store new refresh token and revoke old one (token rotation)
        expires_at = AuthUtils.get_token_expiry_time()
        await DatabaseService.create_refresh_token(
            str(user_data['id']), 
            new_refresh_token_hash, 
            expires_at, 
            user_agent, 
            ip_address
        )
        
        # Revoke old refresh token
        await DatabaseService.revoke_refresh_token(str(matched_token['id']))
        
        return RefreshTokenResponse(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refresh token error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

# Alternative simpler approach - store refresh tokens as JWTs
# This approach is less secure but easier to implement

def create_refresh_token_jwt(user_id: str) -> str:
    """Create JWT-based refresh token"""
    data = {
        "sub": user_id,
        "type": "refresh",
        "jti": str(uuid.uuid4())
    }
    expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return AuthUtils.create_access_token(data, expires_delta)

def decode_refresh_token_jwt(token: str) -> Dict[str, Any]:
    """Decode JWT refresh token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Check if token type is refresh
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

# JWT-based refresh endpoint (simpler alternative)
@router.post("/refresh-jwt", response_model=RefreshTokenResponse)
async def refresh_token_jwt(token_data: TokenRefreshRequest):
    """Refresh access token using JWT-based refresh token"""
    try:
        # Decode refresh token
        payload = decode_refresh_token_jwt(token_data.refresh_token)
        user_id = payload.get("sub")
        jti = payload.get("jti")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        
        # Check if token is blacklisted
        if jti and await DatabaseService.is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked"
            )
        
        # Get user from database
        user = await DatabaseService.get_user_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new access token
        access_token = AuthUtils.create_access_token({"sub": user_id})
        
        return RefreshTokenResponse(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"JWT refresh token error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: Dict[str, Any] = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """User logout"""
    try:
        # Get token from credentials
        token = credentials.credentials
        
        # Decode token to get JTI and expiration
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        jti = payload.get("jti")
        exp = payload.get("exp")
        
        if jti and exp:
            # Convert exp to datetime
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
            
            # Add token to blacklist
            await DatabaseService.blacklist_token(jti, expires_at)
        
        # Revoke all refresh tokens for the user
        await DatabaseService.revoke_all_user_refresh_tokens(current_user["id"])
        
        return MessageResponse(message="Successfully logged out")
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get current user information"""
    # Get fresh user data from database
    user = await DatabaseService.get_user_by_id(current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
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