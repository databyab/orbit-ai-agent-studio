from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.entities import Procedure, Agent
from app.schemas.api_schemas import ProcedureCreate, ProcedureResponse

router = APIRouter(prefix="/api/v2/agents/{agent_id}/procedures", tags=["Procedures"])

@router.get("", response_model=List[ProcedureResponse])
async def list_procedures(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Procedure).where(Procedure.agent_id == agent_id).order_by(Procedure.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=ProcedureResponse, status_code=status.HTTP_201_CREATED)
async def create_procedure(agent_id: UUID, payload: ProcedureCreate, db: AsyncSession = Depends(get_db)):
    stmt = select(Agent).where(Agent.id == agent_id)
    res = await db.execute(stmt)
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    proc = Procedure(
        agent_id=agent_id,
        name=payload.name,
        trigger_description=payload.trigger_description,
        is_active=payload.is_active,
        steps_graph=payload.steps_graph
    )
    db.add(proc)
    await db.commit()
    await db.refresh(proc)
    return proc

@router.put("/{procedure_id}", response_model=ProcedureResponse)
async def update_procedure(
    agent_id: UUID,
    procedure_id: UUID,
    payload: ProcedureCreate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Procedure).where(Procedure.id == procedure_id, Procedure.agent_id == agent_id)
    res = await db.execute(stmt)
    proc = res.scalar_one_or_none()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")

    proc.name = payload.name
    proc.trigger_description = payload.trigger_description
    proc.is_active = payload.is_active
    proc.steps_graph = payload.steps_graph

    await db.commit()
    await db.refresh(proc)
    return proc

@router.delete("/{procedure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_procedure(agent_id: UUID, procedure_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Procedure).where(Procedure.id == procedure_id, Procedure.agent_id == agent_id)
    res = await db.execute(stmt)
    proc = res.scalar_one_or_none()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")

    await db.delete(proc)
    await db.commit()
    return None
