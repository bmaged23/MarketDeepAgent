import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from app.agents.retrieval.agent import create_runner
from app.agents.retrieval.schemas import RetrievalRequest
from app.utils.llm_json import StructuredResponseError

router = APIRouter(prefix="/api", tags=["retrieval agent"])


@router.post("/retrieval")
def retrieve(payload: RetrievalRequest, request: Request):
    try:
        agent = create_runner(request.app.state.settings, request.app.state.search)
        return agent.run(payload.query)
    except (httpx.HTTPError, StructuredResponseError, ValidationError) as exc:
        raise HTTPException(503, "Retrieval model service failed; no successful validation is claimed") from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
