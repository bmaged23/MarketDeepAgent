from pydantic import BaseModel, ConfigDict, Field
from app.application_guide.schemas import PageContext


class ChatRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    query: str=Field(min_length=1,max_length=2000)
    conversation_id: str|None=Field(default=None,min_length=1,max_length=100)
    page_context: PageContext=Field(default_factory=PageContext)


class ProfileUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    first_name: str=Field(min_length=1,max_length=100)
    last_name: str=Field(min_length=1,max_length=100)
    phone: str=Field(default="",max_length=40)
    address: str=Field(default="",max_length=1000)


class PreferenceUpdate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    memory_enabled: bool=Field(strict=True)
