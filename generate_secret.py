# generate_secret.py
# Run this script to generate a secure JWT secret key
import secrets
import string

def generate_secure_jwt_secret(length=64):
    """Generate a cryptographically secure random string for JWT secret"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_secure_password(length=32):
    """Generate a secure database password"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

if __name__ == "__main__":
    print("🔐 Generating secure credentials for your application...\n")
    
    jwt_secret = generate_secure_jwt_secret()
    db_password = generate_secure_password()
    
    print("JWT_SECRET_KEY:")
    print(jwt_secret)
    print("\nDB_PASSWORD:")
    print(db_password)
    
    print("\n⚠️  IMPORTANT: Save these credentials securely!")
    print("   Copy them to your .env file and never commit them to version control.")
    print("   Store them in a password manager for backup.")