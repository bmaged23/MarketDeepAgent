import httpx
import logging
from fastapi import APIRouter,Depends,Request
from pydantic import ValidationError
from app.authentication.dependencies import current_person
from app.assistant.schemas import ChatRequest,ProfileUpdate,PreferenceUpdate
from app.customer_memory.schemas import MemoryEdit
from app.product_reviews.schemas import ProductReview
from app.product_reviews.service import ProductReviewService
from app.application_guide.registry import application_help
from app.database.connection import connection
from app.utils.llm_json import StructuredResponseError
from app.utils.errors import ServiceError

router=APIRouter(prefix="/api",tags=["assistant"])


@router.post("/chat")
def chat(payload:ChatRequest,request:Request,person_id:int=Depends(current_person)):
    try:
        return request.app.state.assistant.chat(person_id,payload)
    except StructuredResponseError as error:
        logging.getLogger(__name__).warning("Assistant structured response failure: %s", error)
        raise ServiceError(503,"Assistant returned an invalid decision. No successful action is claimed; check your cart before retrying a cart change.") from None
    except (httpx.HTTPError,ValidationError,RuntimeError) as error:
        status = error.response.status_code if isinstance(error,httpx.HTTPStatusError) else None
        logging.getLogger(__name__).warning("Assistant service failure type=%s upstream_status=%s",type(error).__name__,status)
        raise ServiceError(503,"Assistant service could not finish this request. Check your cart before retrying a cart change.") from None



@router.get("/application-guide")
def guide(): return application_help()


@router.get("/conversations/{conversation_id}")
def messages(conversation_id:str,request:Request,person_id:int=Depends(current_person)):
    return request.app.state.conversations.messages(person_id,conversation_id)


@router.delete("/conversations")
def clear_conversations(request:Request,person_id:int=Depends(current_person)):
    request.app.state.conversations.clear(person_id)
    return {"cleared":True}


@router.patch("/profile")
def profile(payload:ProfileUpdate,request:Request,person_id:int=Depends(current_person)):
    with connection(request.app.state.settings.database_path,write=True) as conn:
        conn.execute("UPDATE person SET first_name=?,last_name=?,phone=?,address=? WHERE person_id=?",(payload.first_name,payload.last_name,payload.phone,payload.address,person_id))
    return {"updated":True}


@router.get("/preferences")
def preferences(request:Request,person_id:int=Depends(current_person)):
    return {"memory_enabled":request.app.state.memory.enabled(person_id)}


@router.patch("/preferences")
def save_preferences(payload:PreferenceUpdate,request:Request,person_id:int=Depends(current_person)):
    return request.app.state.memory.set_enabled(person_id,payload.memory_enabled)


@router.get("/memories")
def memories(request:Request,person_id:int=Depends(current_person)):
    return request.app.state.memory.list(person_id)


@router.patch("/memories/{memory_id}")
def edit_memory(memory_id:int,payload:MemoryEdit,request:Request,person_id:int=Depends(current_person)):
    result=request.app.state.memory.edit(person_id,memory_id,payload.text)
    result['sync']=request.app.state.memory.sync(person_id,request.app.state.settings.memory_sync_batch_size)
    return result


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id:int,request:Request,person_id:int=Depends(current_person)):
    result=request.app.state.memory.delete(person_id,memory_id)
    result['sync']=request.app.state.memory.sync(person_id,request.app.state.settings.memory_sync_batch_size)
    return result


@router.delete("/memories")
def clear_memories(request:Request,person_id:int=Depends(current_person)):
    result=request.app.state.memory.delete(person_id)
    result['sync']=request.app.state.memory.sync(person_id,request.app.state.settings.memory_sync_batch_size)
    return result


@router.post("/reviews")
def review(payload:ProductReview,request:Request,person_id:int=Depends(current_person)):
    return ProductReviewService(request.app.state.settings.database_path).submit(person_id,payload)
