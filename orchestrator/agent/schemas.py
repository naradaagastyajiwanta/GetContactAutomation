from enum import Enum

from pydantic import BaseModel, Field


class AgentAction(str, Enum):
    got_number = "got_number"
    refused = "refused"
    need_more = "need_more"
    followup = "followup"
    ignored = "ignored"


class AgentResult(BaseModel):
    action: AgentAction
    response_message: str | None = None
    conversation_state: str | None = None
    tool_calls_made: list[str] = Field(default_factory=list)
    reasoning_summary: str | None = None


class AgentContext(BaseModel):
    conversation_id: int | None = None
    university_id: int | None = None
    university_name: str
    province: str | None = None
    contact_phone: str
    push_name: str
    conversation_history: list[dict] = Field(default_factory=list)
    current_state: str
    attempt_count: int = 0
    lessons: list[dict] = Field(default_factory=list)
