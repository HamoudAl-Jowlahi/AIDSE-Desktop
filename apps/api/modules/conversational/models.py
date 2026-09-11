"""
AIDSE Platform — Conversational Analytics Models (Phase 11)

Conversations are scoped per project and optionally per dataset so context
persists across sessions. Messages store the full audit trail: role, content,
and which tools produced the numbers inside assistant answers.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.db.base import Base

if TYPE_CHECKING:
    from apps.api.modules.projects.models import Project


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped["Project"] = relationship("Project")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="conversation",
        cascade="all, delete-orphan", order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} dataset={self.dataset_id}>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 'user' | 'assistant'
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Audit trail for assistant answers: [{tool, args, key_numbers}]
    tools_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # "rules" | "rules+llm"
    generated_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage role={self.role} conv={self.conversation_id}>"
