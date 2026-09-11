from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatMessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    tools_used: Optional[List[Dict[str, Any]]] = None
    generated_by: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationHistoryOut(BaseModel):
    conversation_id: Optional[UUID] = None
    dataset_id: Optional[UUID] = None
    messages: List[ChatMessageOut] = []

    model_config = ConfigDict(from_attributes=True)


class ChatSendRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    dataset_id: Optional[UUID] = None  # required for dataset-scoped tools


class ToolUsageOut(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    key_numbers: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    answer: str
    tools_used: List[ToolUsageOut] = []
    generated_by: str = "rules"
    conversation_id: UUID


ChatResponse.model_rebuild()
