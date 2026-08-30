from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class ProviderRef:
    name: str
    base_url: str
    auth_mode: str = "bearer"
    production_capable: bool = True
    status: str = "active"


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    display_name: str = ""
    structured_output: bool = True
    web_search: bool = False
    context_window: int = 128000
    input_modalities: tuple[str, ...] = ("text",)


@dataclass(frozen=True)
class ModelRoute:
    role: Literal["decision", "context", "hermes"]
    provider: str
    model: str
    pinned: bool = True
    version: int = 1


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    model: str
    messages: list[ChatMessage]
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    response_format: dict[str, Any] | None = None
    reasoning_effort: str | None = None
    tools: list[Any] | None = None
    tool_choice: str | None = None


class UsageMeta(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionChoice(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    index: int = 0
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    id: str
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageMeta | None = None

    @property
    def content(self) -> str:
        if not self.choices:
            return ""
        return self.choices[0].message.content
