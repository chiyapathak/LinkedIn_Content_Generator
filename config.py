# config.py
import os
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # Database settings
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: str = os.getenv("DB_PORT", "5432")
    db_name: str = os.getenv("DB_NAME", "postgenerator")
    
    # JWT settings
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Google AI settings
    google_api_key: str = os.getenv("GOOGLE_API_KEY")
    
    # CORS settings
    allowed_origins: List[str] = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    
    def validate_required_settings(self):
        """Validate that all required settings are present"""
        required_settings = [
            ("DB_PASSWORD", self.db_password),
            ("JWT_SECRET_KEY", self.jwt_secret_key),
            ("GOOGLE_API_KEY", self.google_api_key)
        ]
        
        missing = [name for name, value in required_settings if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        # Validate JWT secret key strength
        if len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")

    class Config:
        env_file = ".env"

# Create global settings instance
settings = Settings()

# Validate settings on import
settings.validate_required_settings()