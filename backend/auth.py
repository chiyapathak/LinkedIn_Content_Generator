# backend/auth.py
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from psycopg2 import pool
import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel, validator
import logging
import re
from config import settings

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PostgreSQL connection pool with secure configuration
try:
    db_pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=5,
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name
    )
    logger.info("Database connection pool initialized successfully")
except Exception as e:
    logger.error(f"Database connection pool initialization failed: {e}")
    raise

# Password hashing with secure configuration
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__rounds=12  # Increased rounds for better security
)

def get_db_connection():
    connection = db_pool.getconn()
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Database connection error"
        )
    try:
        yield connection
    finally:
        db_pool.putconn(connection)

# OAuth2 setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# Secure Models with validation
class User(BaseModel):
    username: str
    password: str
    
    @validator('username')
    def validate_username(cls, v):
        if not v or len(v) < 3:
            raise ValueError('Username must be at least 3 characters long')
        if len(v) > 50:
            raise ValueError('Username must be less than 50 characters')
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return v.lower()  # Store usernames in lowercase
    
    @validator('password')
    def validate_password(cls, v):
        if not v or len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if len(v) > 128:
            raise ValueError('Password must be less than 128 characters')
        # Check for at least one uppercase, one lowercase, one digit
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v

class UserResponse(BaseModel):
    username: str
    message: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Router instance
auth_router = APIRouter()

# Create user endpoint with better security
@auth_router.post("/signup", response_model=UserResponse)
def signup(user: User, db=Depends(get_db_connection)):
    hashed_password = pwd_context.hash(user.password)
    
    try:
        with db.cursor() as cursor:
            # Check if user already exists
            cursor.execute(
                "SELECT username FROM users WHERE username = %s",
                (user.username,)
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Username already exists"
                )
            
            # Insert new user
            cursor.execute(
                "INSERT INTO users (username, password, created_at) VALUES (%s, %s, %s)",
                (user.username, hashed_password, datetime.utcnow()),
            )
            db.commit()
            
        logger.info(f"New user created: {user.username}")
        return UserResponse(username=user.username, message="User created successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during signup for user {user.username}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error during signup"
        )

# Generate JWT token with secure configuration
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),  # Issued at time
        "type": "access"  # Token type
    })
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

# Token endpoint with better error handling
@auth_router.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db_connection)):
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, password FROM users WHERE username = %s",
                (form_data.username.lower(),),
            )
            user = cursor.fetchone()
        
        # Verify user exists and password is correct
        if not user or not pwd_context.verify(form_data.password, user[2]):
            logger.warning(f"Failed login attempt for username: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create access token
        access_token = create_access_token(data={"sub": user[1], "user_id": user[0]})
        logger.info(f"Successful login for user: {user[1]}")
        
        return Token(access_token=access_token, token_type="bearer")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login for user {form_data.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error during login"
        )

# Get current user function for dependency injection
def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        username: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        token_type: str = payload.get("type")
        
        if username is None or user_id is None or token_type != "access":
            raise credentials_exception
            
        return {"username": username, "user_id": user_id}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exception

# Protected endpoint example
@auth_router.get("/me")
def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "user_id": current_user["user_id"],
        "message": f"Hello, {current_user['username']}"
    }