from fastapi import APIRouter

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "Chatbase Replica API",
        "version": "2.0.0"
    }
