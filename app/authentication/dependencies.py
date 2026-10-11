from fastapi import Request
from app.authentication.service import SESSION_COOKIE
from app.utils.errors import ServiceError


def current_person(request: Request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise ServiceError(403, "Cross-origin requests are not supported")
    return request.app.state.sessions.authenticate(request.cookies.get(SESSION_COOKIE),
        request.headers.get("x-csrf-token"), write=request.method not in {"GET", "HEAD", "OPTIONS"})
