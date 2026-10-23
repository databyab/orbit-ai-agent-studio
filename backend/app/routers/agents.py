from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
import uuid

from app.database import get_db
from app.models.entities import Agent, Workspace
from app.schemas.api_schemas import CreateAgentBody, UpdateAgentBody, AgentResponse

router = APIRouter(prefix="/api/v2/agents", tags=["Agents"])

# Default mock workspace helper
async def get_or_create_workspace(db: AsyncSession) -> Workspace:
    stmt = select(Workspace).limit(1)
    res = await db.execute(stmt)
    ws = res.scalar_one_or_none()
    if not ws:
        ws = Workspace(name="Default Workspace", plan_tier="pro")
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
    return ws

@router.get("", response_model=List[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    stmt = select(Agent).order_by(Agent.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: CreateAgentBody, db: AsyncSession = Depends(get_db)):
    ws = await get_or_create_workspace(db)
    agent = Agent(
        workspace_id=ws.id,
        name=payload.name,
        homepage_url=payload.url,
        instructions=payload.instructions or "You are a helpful customer support agent.",
        model=payload.model or "openai/gpt-oss-120b",
        temperature=payload.temp if payload.temp is not None else 0.0,
        visibility=payload.visibility or "private"
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Agent).where(Agent.id == agent_id)
    res = await db.execute(stmt)
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: UUID, payload: UpdateAgentBody, db: AsyncSession = Depends(get_db)):
    stmt = select(Agent).where(Agent.id == agent_id)
    res = await db.execute(stmt)
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if payload.name is not None:
        agent.name = payload.name
    if payload.instructions is not None:
        agent.instructions = payload.instructions
    if payload.model is not None:
        agent.model = payload.model
    if payload.temp is not None:
        agent.temperature = payload.temp
    if payload.visibility is not None:
        agent.visibility = payload.visibility
    if payload.allowedDomains is not None:
        agent.allowed_domains = payload.allowedDomains
    if payload.initialMessages is not None:
        agent.initial_messages = payload.initialMessages
    if payload.suggestedMessages is not None:
        agent.suggested_messages = payload.suggestedMessages
    if payload.channelInstructions is not None:
        agent.channel_instructions = payload.channelInstructions
    if payload.ipRateLimits is not None:
        agent.ip_rate_limits = payload.ipRateLimits
    if payload.spamSettings is not None:
        agent.spam_settings = payload.spamSettings

    await db.commit()
    await db.refresh(agent)
    return agent

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Agent).where(Agent.id == agent_id)
    res = await db.execute(stmt)
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await db.delete(agent)
    await db.commit()
    return None
