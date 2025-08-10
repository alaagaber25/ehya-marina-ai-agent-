import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agents.live_agent import MessageType

from .chat import Chat, Message


class MessageDirection(str, Enum):
    INCOMING = "incoming"  # From user to AI
    OUTGOING = "outgoing"  # From AI to user


class DatabaseService:
    @staticmethod
    async def create_chat(db: AsyncSession, title: str | None = None) -> Chat:
        """Create a new chat session"""
        chat = Chat(title=title or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        return chat

    @staticmethod
    async def save_message(
        db: AsyncSession,
        chat_id: int,
        direction: MessageDirection,
        content_type: MessageType,
        text_content: str | None = None,
        audio_content: bytes | None = None,
        audio_format: str | None = None,
    ) -> Message:
        """Save a message to the database"""
        message = Message(
            chat_id=chat_id,
            direction=direction.value,
            content_type=content_type.value,
            text_content=text_content,
            audio_content=audio_content,
            audio_format=audio_format,
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    async def get_chat_messages(db: AsyncSession, chat_id: uuid.UUID):
        """Get all messages for a chat"""
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at) # type: ignore
        )
        return result.scalars().all()

    @staticmethod
    async def get_all_chats(db: AsyncSession):
        """Get all chat sessions"""
        result = await db.execute(select(Chat).order_by(Chat.created_at.desc())) # type: ignore
        return result.scalars().all()
