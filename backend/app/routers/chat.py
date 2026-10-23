from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from uuid import UUID
import uuid

from app.database import get_db
from app.models.entities import Agent, Conversation, Message, Action, Procedure
from app.schemas.api_schemas import ChatRequest, SubmitToolResultRequest
from app.services.rag import DualStageRAGService
from app.services.tools import SafeToolExecutor
from app.services.procedures import ProcedureEngine
from app.services.orchestrator import AgentOrchestrator
from app.services.auth import SlidingWindowRateLimiter

router = APIRouter(prefix="/api/v2/agents/{agent_id}", tags=["Chat"])

rag_service = DualStageRAGService()
tool_executor = SafeToolExecutor()
procedure_engine = ProcedureEngine()
orchestrator = AgentOrchestrator(rag_service, tool_executor)
rate_limiter = SlidingWindowRateLimiter()

@router.post("/chat")
@router.post("/chat/general")
async def chat_with_agent(
    agent_id: UUID,
    payload: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # General chat bypasses Q&A matching, vector search, and business actions.
    use_knowledge = not request.url.path.endswith("/chat/general")

    # 1. Fetch Agent
    stmt = select(Agent).where(Agent.id == agent_id)
    res = await db.execute(stmt)
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 2. Origin domain check if agent is public
    origin = request.headers.get("origin")
    if agent.allowed_domains and origin:
        clean_origin = origin.replace("https://", "").replace("http://", "")
        if not any(d in clean_origin for d in agent.allowed_domains):
            raise HTTPException(status_code=403, detail="Origin domain is not in the allowed embed domains list.")

    # 3. Retrieve or create Conversation
    conv = None
    conversation_messages = []
    if payload.conversationId:
        conv_stmt = select(Conversation).where(
            Conversation.id == payload.conversationId,
            Conversation.agent_id == agent_id
        ).options(selectinload(Conversation.messages))
        conv_res = await db.execute(conv_stmt)
        conv = conv_res.scalar_one_or_none()
        if conv:
            conversation_messages = list(conv.messages)

    if not conv:
        conv = Conversation(
            agent_id=agent_id,
            user_id=payload.userId,
            channel=request.headers.get("x-chatbase-channel", "widget"),
            messages=[]
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    # 4. Record User Message if present
    if payload.message:
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=payload.message,
            parts=[{"type": "text", "text": payload.message}]
        )
        db.add(user_msg)
        await db.commit()

    # 5. Load Available Actions
    actions = []
    if use_knowledge:
        action_stmt = select(Action).where(Action.agent_id == agent_id)
        action_res = await db.execute(action_stmt)
        actions = action_res.scalars().all()
    action_map = {a.name: a for a in actions}

    # 6. Evaluate Procedure Engine
    matched_procedure = None
    if use_knowledge:
        matched_procedure = await procedure_engine.match_procedure(
            str(agent_id),
            payload.message or "",
            conv.channel,
            db
        )

    if matched_procedure:
        conv.active_procedure_id = matched_procedure.id

    tool_schemas = procedure_engine.filter_tool_schemas(actions, matched_procedure, conv.channel)

    # 7. Execute Turn Stream
    stream_gen = orchestrator.execute_turn_stream(
        agent=agent,
        conversation=conv,
        conversation_messages=conversation_messages,
        user_message=payload.message,
        use_knowledge=use_knowledge,
        tool_schemas=tool_schemas,
        action_map=action_map,
        db_session=db
    )

    return StreamingResponse(
        stream_gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Conversation-Id": str(conv.id)
        }
    )

@router.post("/conversations/{conversation_id}/tool-result")
async def submit_tool_result(
    agent_id: UUID,
    conversation_id: UUID,
    payload: SubmitToolResultRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.agent_id == agent_id
    )
    res = await db.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    tool_msg = Message(
        conversation_id=conv.id,
        role="tool",
        tool_call_id=payload.toolCallId,
        content=str(payload.output),
        parts=[{
            "type": "tool-result",
            "toolCallId": payload.toolCallId,
            "output": payload.output
        }]
    )
    db.add(tool_msg)
    await db.commit()

    return {"status": "success", "message": "Tool result recorded"}
