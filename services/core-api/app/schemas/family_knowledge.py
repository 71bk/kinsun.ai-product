"""Public information only: no elder, tenant, session or caller-selected audience."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FamilyKnowledgeQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000)
    language: Literal["zh-TW", "en-US"] = "zh-TW"


class PublicKnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=512)
    url: str = Field(min_length=1, max_length=4096)
    locator: str = Field(min_length=1, max_length=2048)
    current_status: Literal["current", "unknown"]

    @field_validator("url")
    @classmethod
    def official_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or not parsed.hostname.endswith(".gov.tw")
            or parsed.username is not None
            or parsed.password is not None
            or "\\" in value
            or any(char.isspace() for char in value)
        ):
            raise ValueError("Official source URL required")
        return value


class FamilyKnowledgeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ANSWER", "PARTIAL", "NO_DATA", "CLARIFY", "BLOCKED", "UNAVAILABLE"]
    answer: str = Field(min_length=1, max_length=50000)
    sources: list[PublicKnowledgeSource] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def sources_match_status(self):
        if bool(self.sources) != (self.status in {"ANSWER", "PARTIAL"}):
            raise ValueError("Only supported answers may contain sources")
        if not self.answer.strip():
            raise ValueError("Answer must not be blank")
        return self
