import hashlib
import hmac
import secrets


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def verify_password(password, stored):
    try:
        if stored.startswith("pbkdf2_sha256$"):
            _, iterations, salt, digest = stored.split("$")
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
        else:
            # Preserve login for legacy seeded accounts.
            salt, digest = stored.split("$", 1)
            actual = hashlib.sha256((salt + password).encode()).hexdigest()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False
