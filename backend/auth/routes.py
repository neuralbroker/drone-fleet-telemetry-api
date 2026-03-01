"""
Authentication routes for the Drone Fleet Telemetry API.

Provides REST endpoints for user registration, login, and
token refresh using JWT authentication.
"""
import json
import logging
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from backend.config import settings
from backend.fleet.models import User, UserCreate, UserLogin, Token, UserRole, TokenData
from backend.auth.jwt_handler import (
    create_access_token,
    decode_token,
    get_password_hash,
    verify_password
)

logger = logging.getLogger(__name__)

# Router
router = APIRouter(prefix="/auth", tags=["Authentication"])

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# In-memory user storage (replace with database in production)
# Key: username, Value: User dict with hashed password
_users_db: dict = {}


async def get_current_user(
    token: str = Depends(oauth2_scheme)
) -> TokenData:
    """
    Dependency to get current authenticated user from JWT token.
    
    Args:
        token: JWT token from Authorization header
        
    Returns:
        TokenData with user information
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = decode_token(token)
    if token_data is None:
        raise credentials_exception
    
    return token_data


async def get_current_admin(
    current_user: TokenData = Depends(get_current_user)
) -> TokenData:
    """
    Dependency to require admin role.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        TokenData if user is admin
        
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def _get_user(username: str) -> dict | None:
    """Get user from in-memory storage."""
    return _users_db.get(username)


def _save_user(user_create: UserCreate, user_id: UUID) -> User:
    """
    Save user to in-memory storage.
    
    Args:
        user_create: User creation data
        user_id: Generated user ID
        
    Returns:
        Created User object
    """
    hashed_password = get_password_hash(user_create.password)
    
    user_dict = {
        "id": str(user_id),
        "username": user_create.username,
        "role": user_create.role.value,
        "hashed_password": hashed_password,
    }
    
    _users_db[user_create.username] = user_dict
    
    return User(
        id=user_id,
        username=user_create.username,
        role=user_create.role
    )


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(user_create: UserCreate):
    """
    Register a new user.
    
    Args:
        user_create: User registration data
        
    Returns:
        Created user object
        
    Raises:
        HTTPException: If username already exists
    """
    # Check if username exists
    if _get_user(user_create.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Create user
    user_id = UUID(int=len(_users_db) + 1)  # Simple ID generation
    user = _save_user(user_create, user_id)
    
    logger.info(f"New user registered: {user.username}")
    
    return user


@router.post("/login", response_model=Token)
async def login(user_login: UserLogin):
    """
    Authenticate user and return JWT token.
    
    Args:
        user_login: User credentials
        
    Returns:
        Access token and expiration info
        
    Raises:
        HTTPException: If credentials are invalid
    """
    # Get user from storage
    user_dict = _get_user(user_login.username)
    
    if not user_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not verify_password(user_login.password, user_dict["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token = create_access_token(
        user_id=UUID(user_dict["id"]),
        username=user_dict["username"],
        role=UserRole(user_dict["role"])
    )
    
    logger.info(f"User logged in: {user_login.username}")
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/token", response_model=Token)
async def login_oauth2(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 compatible login endpoint.
    
    Supports form data with username and password fields.
    
    Args:
        form_data: OAuth2 form data
        
    Returns:
        Access token and expiration info
    """
    # Get user from storage
    user_dict = _get_user(form_data.username)
    
    if not user_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token = create_access_token(
        user_id=UUID(user_dict["id"]),
        username=user_dict["username"],
        role=UserRole(user_dict["role"])
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me", response_model=TokenData)
async def get_me(current_user: TokenData = Depends(get_current_user)):
    """
    Get current user information.
    
    Requires authentication.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Current user data
    """
    return current_user


@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: TokenData = Depends(get_current_user)):
    """
    Refresh JWT token.
    
    Issues a new token with the same user credentials.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        New access token
    """
    access_token = create_access_token(
        user_id=current_user.user_id,
        username=current_user.username,
        role=current_user.role
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


# Create default admin user for testing
def create_default_admin():
    """Create a default admin user for initial testing."""
    if "admin" not in _users_db:
        user_create = UserCreate(
            username="admin",
            password="admin123",
            role=UserRole.ADMIN
        )
        _save_user(user_create, UUID("00000000-0000-0000-0000-000000000001"))
        logger.info("Default admin user created")


# Initialize on module load
create_default_admin()
