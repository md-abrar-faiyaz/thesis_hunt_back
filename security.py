import os
import hashlib

try:
    import bcrypt
    USE_BCRYPT = True
except ImportError:
    USE_BCRYPT = False


def hash_password(password: str) -> str:
    """Hash raw password string using bcrypt (if available) or PBKDF2 HMAC SHA-256."""
    if USE_BCRYPT:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ':' + hashed.hex()


def verify_password(password: str, pass_hash: str) -> bool:
    """Verify input password against stored hash."""
    if USE_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), pass_hash.encode('utf-8'))
        except Exception:
            return False
            
    try:
        salt_hex, hash_hex = pass_hash.split(':')
        salt = bytes.fromhex(salt_hex)
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return hashed.hex() == hash_hex
    except Exception:
        return False
