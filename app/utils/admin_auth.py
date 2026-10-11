import secrets
from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def require_admin(request: Request, key: str | None = Security(header)):
    expected = request.app.state.settings.admin_api_key.get_secret_value()
    if not expected:
        raise HTTPException(503, "Product administration is disabled; configure ADMIN_API_KEY")
    if not key or not secrets.compare_digest(key, expected):
        raise HTTPException(401, "Invalid administrator credentials")
