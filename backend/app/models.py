"""Profile / CV data model shared by the scraper, the LLM agents and the exporters."""

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _id() -> str:
    return uuid4().hex[:10]


class Item(BaseModel):
    id: str = Field(default_factory=_id)
    include: bool = True


class Basics(BaseModel):
    full_name: str = ""
    headline: str = ""
    location: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    websites: list[str] = []
    summary: str = ""


class Experience(Item):
    title: str = ""
    company: str = ""
    employment_type: str = ""
    location: str = ""
    start: str = ""
    end: str = ""
    current: bool = False
    description: str = ""
    skills: list[str] = []


class Education(Item):
    school: str = ""
    degree: str = ""
    field: str = ""
    start: str = ""
    end: str = ""
    grade: str = ""
    description: str = ""


class Certification(Item):
    name: str = ""
    issuer: str = ""
    issued: str = ""
    expires: str = ""
    credential_id: str = ""
    url: str = ""


class Skill(Item):
    name: str = ""


class Language(Item):
    name: str = ""
    proficiency: str = ""


class Project(Item):
    name: str = ""
    start: str = ""
    end: str = ""
    url: str = ""
    description: str = ""
    skills: list[str] = []


class Volunteering(Item):
    role: str = ""
    organization: str = ""
    cause: str = ""
    start: str = ""
    end: str = ""
    current: bool = False
    description: str = ""


class Honor(Item):
    title: str = ""
    issuer: str = ""
    date: str = ""
    description: str = ""


class Publication(Item):
    title: str = ""
    publisher: str = ""
    date: str = ""
    url: str = ""
    description: str = ""


class Course(Item):
    name: str = ""
    number: str = ""


SectionKey = Literal[
    "summary", "experience", "education", "skills", "certifications", "languages",
    "projects", "volunteering", "honors", "publications", "courses",
]

DEFAULT_ORDER: list[SectionKey] = [
    "summary", "experience", "education", "skills", "certifications", "languages",
    "projects", "volunteering", "honors", "publications", "courses",
]


class Profile(BaseModel):
    basics: Basics = Basics()
    experience: list[Experience] = []
    education: list[Education] = []
    skills: list[Skill] = []
    certifications: list[Certification] = []
    languages: list[Language] = []
    projects: list[Project] = []
    volunteering: list[Volunteering] = []
    honors: list[Honor] = []
    publications: list[Publication] = []
    courses: list[Course] = []


class Target(BaseModel):
    """The job the CV is aimed at: drives the AI agents and the keyword match."""
    title: str = ""
    company: str = ""
    offer_url: str = ""
    offer_text: str = ""
    keywords: list[str] = []


class CVSettings(BaseModel):
    language: Literal["fr", "en"] = "fr"
    # Enabled sections, in display order.
    sections: list[SectionKey] = DEFAULT_ORDER
    accent: str = Field(default="#111111", pattern=r"^#[0-9a-fA-F]{6}$")  # name + section titles color
    target: Target = Target()


class CV(BaseModel):
    profile: Profile
    settings: CVSettings = CVSettings()
