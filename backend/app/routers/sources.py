from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.entities import Agent, Source, QnaItem
from app.schemas.api_schemas import CreateSourceBody, SourceResponse, QnaItemResponse
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/api/v2/agents/{agent_id}/sources", tags=["Sources"])
ingestion_service = IngestionService()

@router.get("", response_model=List[SourceResponse])
async def list_sources(agent_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Source).where(Source.agent_id == agent_id).order_by(Source.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

async def process_source_indexing(source_id: UUID, agent_id: UUID, raw_text: str):
    from app.database import AsyncSessionLocal
    try:
        count = await ingestion_service.index_content(str(agent_id), str(source_id), raw_text)
        async with AsyncSessionLocal() as session:
            stmt = select(Source).where(Source.id == source_id)
            res = await session.execute(stmt)
            src = res.scalar_one_or_none()
            if src:
                src.status = "Synced"
                src.size_bytes = len(raw_text.encode("utf-8"))
                await session.commit()
    except Exception as e:
        async with AsyncSessionLocal() as session:
            stmt = select(Source).where(Source.id == source_id)
            res = await session.execute(stmt)
            src = res.scalar_one_or_none()
            if src:
                src.status = "Failed"
                src.error_message = str(e)
                await session.commit()

@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    agent_id: UUID,
    payload: CreateSourceBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Agent).where(Agent.id == agent_id)
    res = await db.execute(stmt)
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    source_type = payload.type
    source_name = getattr(payload, "name", "Web Link" if source_type == "link" else "Source")
    
    source = Source(
        agent_id=agent_id,
        name=source_name,
        type=source_type,
        status="Syncing",
        config=payload.model_dump()
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    if source_type == "text":
        content = payload.content
        background_tasks.add_task(process_source_indexing, source.id, agent_id, content)

    elif source_type == "qna":
        qna = QnaItem(
            agent_id=agent_id,
            source_id=source.id,
            questions=payload.questions,
            answer=payload.answer
        )
        db.add(qna)
        await db.commit()
        # Q&A also gets indexed into vectors
        qna_text = f"Questions: {', '.join(payload.questions)}\nAnswer: {payload.answer}"
        background_tasks.add_task(process_source_indexing, source.id, agent_id, qna_text)

    elif source_type == "link":
        async def crawl_and_index():
            from app.database import AsyncSessionLocal
            try:
                text = await ingestion_service.crawl_url(payload.url)
                await process_source_indexing(source.id, agent_id, text)
            except Exception as e:
                async with AsyncSessionLocal() as session:
                    stmt = select(Source).where(Source.id == source.id)
                    res = await session.execute(stmt)
                    src = res.scalar_one_or_none()
                    if src:
                        src.status = "Failed"
                        src.error_message = str(e)
                        await session.commit()

        background_tasks.add_task(crawl_and_index)

    return source

@router.post("/upload", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_file_source(
    agent_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Agent).where(Agent.id == agent_id)
    res = await db.execute(stmt)
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    content = await file.read()
    filename = file.filename or "uploaded_file"
    ext = filename.split(".")[-1].lower()

    if ext not in ["pdf", "docx", "txt", "doc"]:
        raise HTTPException(status_code=400, detail="Only .pdf, .docx, and .txt files are supported")

    source = Source(
        agent_id=agent_id,
        name=filename,
        type="file",
        status="Syncing",
        size_bytes=len(content)
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    async def parse_and_index():
        try:
            if ext == "pdf":
                raw_text = ingestion_service.extract_pdf(content)
            elif ext == "docx":
                raw_text = ingestion_service.extract_docx(content)
            else:
                raw_text = content.decode("utf-8", errors="ignore")

            await process_source_indexing(source.id, agent_id, raw_text)
        except Exception as e:
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                stmt = select(Source).where(Source.id == source.id)
                res = await session.execute(stmt)
                src = res.scalar_one_or_none()
                if src:
                    src.status = "Failed"
                    src.error_message = str(e)
                    await session.commit()

    background_tasks.add_task(parse_and_index)
    return source

@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(agent_id: UUID, source_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Source).where(Source.id == source_id, Source.agent_id == agent_id)
    res = await db.execute(stmt)
    source = res.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Purge vectors from Qdrant immediately
    await ingestion_service.purge_source(str(agent_id), str(source_id))

    await db.delete(source)
    await db.commit()
    return None
