from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.models.entities import Conversation, Message, QnaItem, Source
from app.schemas.api_schemas import (
    ConversationResponse, MessageResponse, MessageFeedbackRequest, QnaItemCreate, QnaItemResponse
)

router = APIRouter(prefix="/api/v2/agents/{agent_id}/conversations", tags=["Conversations"])

@router.get("", response_model=List[ConversationResponse])
async def list_conversations(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Conversation)
        .where(Conversation.agent_id == agent_id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(agent_id: UUID, conversation_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.agent_id == agent_id)
        .options(selectinload(Conversation.messages))
    )
    res = await db.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv

@router.patch("/{conversation_id}/messages/{message_id}/feedback")
async def update_message_feedback(
    agent_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    payload: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Message).where(Message.id == message_id, Message.conversation_id == conversation_id)
    res = await db.execute(stmt)
    msg = res.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    msg.feedback = payload.feedback
    msg.feedback_comment = payload.feedbackComment
    await db.commit()

    return {"status": "success", "message": "Feedback recorded"}

@router.post("/{conversation_id}/messages/{message_id}/revise", response_model=QnaItemResponse)
async def revise_message_to_qna(
    agent_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    payload: QnaItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Implements Chatbase's Revise flywheel (Finding FIND-E02):
    Correcting a response saves it directly as a canonical Q&A item,
    which acts as high-priority deterministic grounding for all future turns.
    """
    stmt = select(Message).where(Message.id == message_id, Message.conversation_id == conversation_id)
    res = await db.execute(stmt)
    msg = res.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Update message content to match revised answer
    msg.content = payload.answer
    msg.feedback = "thumbs_up"

    # Create QnA Item
    qna = QnaItem(
        agent_id=agent_id,
        questions=payload.questions,
        answer=payload.answer
    )
    db.add(qna)
    await db.commit()
    await db.refresh(qna)

    return qna
