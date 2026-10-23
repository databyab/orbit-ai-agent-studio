from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import engine, Base
from app.routers import health, agents, sources, chat, procedures, conversations, widget
from app.services.ingestion import IngestionService

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables if they do not exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Startup: ensure Qdrant collection exists
    ingestion = IngestionService()
    await ingestion.ensure_collection()
    
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(
    title="Chatbase Replica API",
    version="2.0.0",
    description="Clean-room replica of Chatbase AI agent builder and RAG platform.",
    lifespan=lifespan
)

# CORS Middleware (allows widget embedding from external domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
)

# Include Routers
app.include_router(health.router)
app.include_router(agents.router)
app.include_router(sources.router)
app.include_router(chat.router)
app.include_router(procedures.router)
app.include_router(conversations.router)
app.include_router(widget.router)

@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": "2.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json"
    }
