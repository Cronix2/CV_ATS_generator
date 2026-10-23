from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from app.models import CV, Profile


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['1'] = '1'


class ProfileInput(Input):
    profile: Profile


class CVInput(Input):
    cv: CV


class OfferInput(Input):
    title: str = Field(default='', max_length=500)
    company: str = Field(default='', max_length=500)
    text: str = Field(min_length=1, max_length=100000)
    url: str = Field(default='', max_length=2048)


class ImportOffer(Input):
    url: str = Field(min_length=1, max_length=2048)


class Provider(Input):
    provider_ref: str = Field(default='default', pattern=r'^[A-Za-z0-9_-]{1,64}$')


class ReviewInput(CVInput):
    offer: OfferInput | None = None
    agents: list[Literal['summary','experience','skills','cleanup','ats_review']] = Field(
        default_factory=lambda: ['summary','experience','skills','cleanup','ats_review'], min_length=1, max_length=5)
    llm: Provider = Field(default_factory=Provider)


class RenderInput(CVInput):
    format: Literal['pdf','docx'] = 'pdf'


class MessageInput(Input):
    instruction: str = Field(min_length=1, max_length=10000)
    llm: Provider = Field(default_factory=Provider)


class ConversationInput(CVInput):
    pass


class WorkflowInput(CVInput):
    offer: OfferInput
    llm: Provider = Field(default_factory=Provider)
    use_ai: bool = True


class Approval(Input):
    version: int = Field(ge=1)
    digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmed: Literal[True]


class ScrapeInput(Input):
    profile_url: str = Field(min_length=1, max_length=2048)
    email: SecretStr | None = None
    password: SecretStr | None = None
    session_id: UUID | None = None


class CodeInput(Input):
    code: SecretStr


class JobView(BaseModel):
    id: UUID
    status: str
    percent: int
    messages: list[str]
    error: dict | None = None
    result: dict | None = None
    attempt: int
    expires_at: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
