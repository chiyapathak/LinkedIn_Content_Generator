# backend/gemini_utils.py
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPIError
import logging
from config import settings
from pydantic import BaseModel, validator
from typing import Literal
import time

# Configure logging
logger = logging.getLogger(__name__)

# Configure Gemini AI with secure API key
try:
    genai.configure(api_key=settings.google_api_key)
    model = genai.GenerativeModel("models/gemini-1.5-pro")
    logger.info("Gemini AI model initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Gemini AI: {e}")
    raise

# Input validation models
class PostGenerationRequest(BaseModel):
    mood: Literal[
        "professional", "casual", "inspirational", "humorous", 
        "thought-provoking", "celebratory", "motivational"
    ]
    length: Literal["short", "medium", "long"]
    language: Literal["english", "spanish", "french", "german", "italian", "portuguese"]
    topic: str = ""
    
    @validator('topic')
    def validate_topic(cls, v):
        if len(v) > 200:
            raise ValueError('Topic must be less than 200 characters')
        return v.strip()

# Rate limiting (simple in-memory implementation)
class RateLimiter:
    def __init__(self):
        self.requests = {}
    
    def is_allowed(self, user_id: int, max_requests: int = 10, window_minutes: int = 60) -> bool:
        current_time = time.time()
        window_start = current_time - (window_minutes * 60)
        
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # Remove old requests outside the window
        self.requests[user_id] = [req_time for req_time in self.requests[user_id] if req_time > window_start]
        
        # Check if under the limit
        if len(self.requests[user_id]) < max_requests:
            self.requests[user_id].append(current_time)
            return True
        
        return False

# Global rate limiter instance
rate_limiter = RateLimiter()

def generate_linkedin_post(request: PostGenerationRequest, user_id: int) -> dict:
    """
    Generate a LinkedIn post using Google's Gemini AI with proper error handling and rate limiting.
    
    Args:
        request: PostGenerationRequest containing mood, length, language, and optional topic
        user_id: ID of the user making the request (for rate limiting)
    
    Returns:
        dict: Contains either the generated post or error information
    """
    
    # Check rate limiting
    if not rate_limiter.is_allowed(user_id):
        logger.warning(f"Rate limit exceeded for user {user_id}")
        return {
            "success": False,
            "error": "Rate limit exceeded. Please try again later.",
            "error_type": "rate_limit"
        }
    
    # Build enhanced prompt
    length_mapping = {
        "short": "1-2 sentences (maximum 280 characters)",
        "medium": "2-4 sentences (maximum 500 characters)", 
        "long": "4-6 sentences (maximum 800 characters)"
    }
    
    mood_instructions = {
        "professional": "Use formal language, industry insights, and business-focused content",
        "casual": "Use conversational tone, relatable examples, and friendly language",
        "inspirational": "Focus on motivation, personal growth, and positive messages",
        "humorous": "Include light humor, witty observations, but keep it professional",
        "thought-provoking": "Ask questions, share insights, encourage discussion",
        "celebratory": "Acknowledge achievements, milestones, or positive news",
        "motivational": "Encourage action, share success stories, inspire others"
    }
    
    base_prompt = f"""
    Create a LinkedIn post with the following specifications:
    
    - Mood/Tone: {mood_instructions.get(request.mood, request.mood)}
    - Length: {length_mapping.get(request.length, request.length)}
    - Language: {request.language.title()}
    """
    
    if request.topic:
        base_prompt += f"- Topic/Focus: {request.topic}\n"
    
    base_prompt += """
    Requirements:
    - Make it engaging and likely to generate meaningful engagement
    - Include relevant hashtags (2-5 maximum)
    - Ensure it's appropriate for a professional network
    - Make it authentic and valuable to the reader
    - Do not include any promotional content or sales pitches
    - Format it properly for LinkedIn (use line breaks where appropriate)
    
    Generate only the post content, no additional explanations.
    """
    
    try:
        logger.info(f"Generating post for user {user_id} with mood: {request.mood}, length: {request.length}")
        
        # Generate content with timeout
        response = model.generate_content(
            base_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,  # Balance creativity with consistency
                top_p=0.8,
                top_k=40,
                max_output_tokens=1000,
            )
        )
        
        if not response or not response.text:
            logger.error("Empty response from Gemini API")
            return {
                "success": False,
                "error": "Failed to generate content. Please try again.",
                "error_type": "empty_response"
            }
        
        generated_post = response.text.strip()
        
        # Basic content validation
        if len(generated_post) < 10:
            logger.warning("Generated post too short")
            return {
                "success": False,
                "error": "Generated content too short. Please try again.",
                "error_type": "content_too_short"
            }
        
        logger.info(f"Successfully generated post for user {user_id}")
        return {
            "success": True,
            "post": generated_post,
            "metadata": {
                "mood": request.mood,
                "length": request.length,
                "language": request.language,
                "character_count": len(generated_post)
            }
        }
        
    except ResourceExhausted:
        logger.error("Gemini API quota exceeded")
        return {
            "success": False,
            "error": "AI service quota exceeded. Please try again later.",
            "error_type": "quota_exceeded"
        }
    
    except GoogleAPIError as e:
        logger.error(f"Google API error: {e}")
        return {
            "success": False,
            "error": "AI service temporarily unavailable. Please try again later.",
            "error_type": "api_error"
        }
    
    except Exception as e:
        logger.error(f"Unexpected error during post generation for user {user_id}: {e}")
        return {
            "success": False,
            "error": "An unexpected error occurred. Please try again.",
            "error_type": "unexpected_error"
        }

def get_generation_stats(user_id: int) -> dict:
    """Get rate limiting stats for a user"""
    current_time = time.time()
    window_start = current_time - (60 * 60)  # 1 hour window
    
    user_requests = rate_limiter.requests.get(user_id, [])
    recent_requests = [req for req in user_requests if req > window_start]
    
    return {
        "requests_in_last_hour": len(recent_requests),
        "max_requests_per_hour": 10,
        "remaining_requests": max(0, 10 - len(recent_requests))
    }