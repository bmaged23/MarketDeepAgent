from fastapi import APIRouter, Request, Response, Depends
from app.authentication.dependencies import current_person
from app.authentication.service import SESSION_COOKIE, CSRF_COOKIE
from app.database.connection import connection

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/me")
def me(request: Request, person_id: int = Depends(current_person)):
    with connection(request.app.state.settings.database_path) as conn:
        return dict(conn.execute("SELECT person_id,first_name,last_name,email,phone,address FROM person WHERE person_id=?", (person_id,)).fetchone())


@router.post("/logout")
def logout(request: Request, response: Response, person_id: int = Depends(current_person)):
    request.app.state.sessions.revoke(request.cookies[SESSION_COOKIE])
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    return {"signed_out": True}
