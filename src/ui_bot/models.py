from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    current_url: HttpUrl | None = None
    answers: dict[str, str] = Field(default_factory=dict)


class AgentAction(BaseModel):
    type: Literal[
        "navigate",
        "snapshot",
        "fill",
        "click",
        "scroll",
        "back",
        "ask",
        "save_location",
    ]
    value: str | None = None
    selector: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    reason: str | None = None


class PageField(BaseModel):
    label: str
    selector: str
    field_type: str
    required: bool = False
    value: str | None = None


class PageSnapshot(BaseModel):
    url: str
    title: str
    fields: list[PageField] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)
    actions: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    message: str
    question: str | None = None
    actions: list[AgentAction] = Field(default_factory=list)
    snapshot: PageSnapshot | None = None


class LocationCreate(BaseModel):
    session_id: str
    name: str
    url: str
    title: str = ""
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SavedLocation(LocationCreate):
    id: int
    created_at: str


class FeedbackCreate(BaseModel):
    session_id: str
    trace_id: str | None = None
    kind: Literal["approve", "reject", "correct", "done"]
    target_action: AgentAction | None = None
    url: str = ""
    page_title: str = ""
    comment: str = ""
    correction: dict[str, Any] = Field(default_factory=dict)
    promote_to_template: bool = True


class StoredFeedback(FeedbackCreate):
    id: int
    created_at: str


class WorkflowTemplate(BaseModel):
    id: int
    kind: str
    page_url_pattern: str
    field_label: str = ""
    selector: str = ""
    action: str = ""
    confidence: float = 1.0
    uses: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class WorkflowRun(BaseModel):
    id: str
    session_id: str
    goal: str
    status: str
    created_at: str
    updated_at: str
