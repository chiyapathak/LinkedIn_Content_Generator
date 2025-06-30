# main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer
import logging
from contextlib import asynccontextmanager

from backend.gemini_utils import generate_linkedin_post, PostGenerationRequest, get_generation_stats
from backend.auth import auth_router, get_current_user
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Application lifespan events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application starting up...")
    logger.info(f"Allowed origins: {settings.allowed_origins}")
    yield
    # Shutdown
    logger.info("Application shutting down...")

# Create FastAPI app with security configurations
app = FastAPI(
    title="LinkedIn Post Generator API",
    description="A secure API for generating LinkedIn posts using AI",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.db_host == "localhost" else None,  # Hide docs in production
    redoc_url="/redoc" if settings.db_host == "localhost" else None
)

# Security middlewares
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "*.yourdomain.com"]  # Adjust for your domain
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # Specific origins only
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Specific methods only
    allow_headers=["Authorization", "Content-Type"],  # Specific headers only
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Include authentication router
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# Security scheme for documentation
security = HTTPBearer()

@app.get("/")
def read_root():
    """Root endpoint with basic API information"""
    return {
        "message": "Welcome to the LinkedIn Post Generator API",
        "version": "1.0.0",
        "status": "active",
        "endpoints": {
            "auth": "/auth",
            "generate": "/generate",
            "stats": "/stats"
        }
    }

@app.post("/generate")
def generate_post(
    request: PostGenerationRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate a LinkedIn post with AI.
    Requires authentication.
    """
    logger.info(f"Post generation request from user {current_user['username']}")
    
    try:
        result = generate_linkedin_post(request, current_user["user_id"])
        
        if not result["success"]:
            # Log the error but don't expose internal details
            logger.warning(f"Post generation failed for user {current_user['user_id']}: {result.get('error_type', 'unknown')}")
            
            # Return appropriate HTTP status based on error type
            if result.get("error_type") == "rate_limit":
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=result["error"]
                )
            elif result.get("error_type") == "quota_exceeded":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=result["error"]
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=result["error"]
                )
        
        return {
            "success": True,
            "post": result["post"],
            "metadata": result["metadata"],
            "user": current_user["username"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in generate_post endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

@app.get("/stats")
def get_user_stats(current_user: dict = Depends(get_current_user)):
    """
    Get user's generation statistics and rate limiting info.
    Requires authentication.
    """
    try:
        stats = get_generation_stats(current_user["user_id"])
        return {
            "user": current_user["username"],
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting stats for user {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve statistics"
        )

@app.get("/health")
def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": "2025-06-30T00:00:00Z"
    }

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {"error": "Not found", "status_code": 404}

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return {"error": "Internal server error", "status_code": 500}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",  # Bind to localhost only for security
        port=8000,
        reload=True if settings.db_host == "localhost" else False,
        log_level="info"
    )