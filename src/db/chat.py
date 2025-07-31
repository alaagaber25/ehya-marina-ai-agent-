from datetime import datetime

from sqlalchemy.sql import func
from sqlmodel import Column, DateTime, Field, LargeBinary, Relationship, SQLModel, Text


class Chat(SQLModel, table=True):
    __tablename__ = "chats"  # type: ignore
    id: int = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )

    updated_at: datetime = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"onupdate": func.now(), "server_default": func.now()},
    )

    title: str | None = None
    is_active: bool = True

    # Relationship to messages
    messages: list["Message"] = Relationship(back_populates="chat")


class Message(SQLModel, table=True):
    __tablename__ = "messages"  # type: ignore
    id: int = Field(default=None, primary_key=True)
    chat_id: int = Field(foreign_key="chats.id", index=True)
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )

    # Message metadata
    direction: str  # incoming/outgoing
    content_type: str  # text/audio/transcription/etc

    # Content fields
    text_content: str | None = Field(sa_column=Column(Text), default=None)
    audio_content: bytes | None = Field(sa_column=Column(LargeBinary), default=None)
    audio_format: str | None = None

    # Relationships
    chat: Chat | None = Relationship(back_populates="messages")
