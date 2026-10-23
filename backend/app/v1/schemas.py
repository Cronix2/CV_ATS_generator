from copy import deepcopy
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from app.models import CV, Profile
from app.v1.crypto import digest


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"

    @model_validator(mode="before")
    @classmethod
    def stable_item_ids(cls, value):
        # Retry the same JSON without regenerating UUID defaults before fingerprinting it.
        if not isinstance(value, dict):
            return value
        value = deepcopy(value)
        profile = value.get("profile")
        if profile is None and isinstance(value.get("cv"), dict):
            profile = value["cv"].get("profile")
        if isinstance(profile, dict):
            for section, items in profile.items():
                if isinstance(items, list):
                    for index, item in enumerate(items):
                        if isinstance(item, dict) and not item.get("id"):
                            item["id"] = digest([section, index, item])[:32]
        return value

    @model_validator(mode="after")
    def unique_item_ids(self):
        profile = getattr(self, "profile", None) or getattr(
            getattr(self, "cv", None), "profile", None
        )
        if profile:
            for section in type(profile).model_fields:
                items = getattr(profile, section)
                if isinstance(items, list) and len({i.id for i in items}) != len(items):
                    raise ValueError("Duplicate item IDs")
        return self


class ProfileInput(Input):
    profile: Profile


class CVInput(Input):
    cv: CV


class OfferInput(Input):
    title: str = Field(default="", max_length=500)
    company: str = Field(default="", max_length=500)
    text: str = Field(min_length=1, max_length=100000)
    url: str = Field(default="", max_length=2048)


class ImportOffer(Input):
    url: str = Field(min_length=1, max_length=2048)


class Provider(Input):
    provider_ref: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ReviewInput(CVInput):
    offer: OfferInput | None = None
    agents: list[
        Literal["summary", "experience", "skills", "cleanup", "ats_review"]
    ] = Field(
        default_factory=lambda: [
            "summary",
            "experience",
            "skills",
            "cleanup",
            "ats_review",
        ],
        min_length=1,
        max_length=5,
    )
    llm: Provider = Field(default_factory=Provider)


class RenderInput(CVInput):
    format: Literal["pdf", "docx"] = "pdf"


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
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
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
    captcha_expires_in: int | None = None
    expires_at: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str


class ResourceView(BaseModel):
    id: UUID
    kind: str
    version: int
    data: dict
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class ResourcePage(BaseModel):
    items: list[ResourceView]
    next_cursor: str | None = None


class ATSCheck(BaseModel):
    label: str
    ok: bool
    hint: str


class ATSResult(BaseModel):
    keywords: list[str]
    found: list[str]
    missing: list[str]
    percent: int | None
    score: int
    checks: list[ATSCheck]
    suggested_keywords: list[str]
