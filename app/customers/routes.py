from fastapi import APIRouter, Request, Response
from app.utils.errors import ServiceError
from app.customers.schemas import RegisterRequest, LoginRequest

router = APIRouter(prefix="/api", tags=["customers"])


@router.post("/register")
def register(payload: RegisterRequest, request: Request, response: Response):
    if request.headers.get("origin") and request.headers["origin"] != str(request.base_url).rstrip("/"):
        raise ServiceError(403, "Cross-origin sign-in is not allowed")
    result = request.app.state.customers.register(payload)
    request.app.state.sessions.cookies(response, result["person_id"])
    return result


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response):
    if request.headers.get("origin") and request.headers["origin"] != str(request.base_url).rstrip("/"):
        raise ServiceError(403, "Cross-origin sign-in is not allowed")
    result = request.app.state.customers.login(payload)
    request.app.state.sessions.cookies(response, result["person_id"])
    return result
