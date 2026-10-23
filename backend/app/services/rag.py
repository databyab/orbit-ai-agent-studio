from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from app.models.entities import QnaItem
from app.config import get_settings

settings = get_settings()

class DualStageRAGService:
    def __init__(self, qdrant_client: Optional[AsyncQdrantClient] = None):
        self.qdrant = qdrant_client or AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        self.collection_name = settings.QDRANT_COLLECTION
        self._encoder = None

    def get_encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(settings.EMBEDDING_MODEL)
        return self._encoder

    async def check_qna_override(self, agent_id: str, query: str, session: AsyncSession) -> Optional[str]:
        """
        Stage 1: Checks Q&A items for deterministic ground truth override.
        Returns the exact answer word-for-word if query matches any question variant.
        """
        stmt = select(QnaItem).where(QnaItem.agent_id == agent_id)
        result = await session.execute(stmt)
        qna_items = result.scalars().all()
        
        if not qna_items:
            return None

        clean_query = query.strip().lower()
        
        # 1. Exact string / substring match
        for item in qna_items:
            for q in item.questions:
                if clean_query == q.strip().lower() or clean_query in q.strip().lower():
                    return item.answer

        # 2. High-confidence semantic cosine similarity match
        encoder = self.get_encoder()
        query_vector = encoder.encode(clean_query, convert_to_numpy=True)
        
        best_match_score = 0.0
        best_answer = None

        import numpy as np
        for item in qna_items:
            for q in item.questions:
                q_vec = encoder.encode(q.strip().lower(), convert_to_numpy=True)
                score = float(np.dot(query_vector, q_vec) / (np.linalg.norm(query_vector) * np.linalg.norm(q_vec) + 1e-9))
                if score > best_match_score:
                    best_match_score = score
                    best_answer = item.answer

        if best_match_score >= 0.88: # High confidence cutoff
            return best_answer

        return None

    async def retrieve_chunks(self, agent_id: str, query: str, top_k: int = 4) -> List[str]:
        """
        Stage 2: Vector search in Qdrant with tenant isolation filter.
        """
        try:
            encoder = self.get_encoder()
            query_vector = encoder.encode(query, convert_to_numpy=True).tolist()

            results = await self.qdrant.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(key="agent_id", match=qmodels.MatchValue(value=str(agent_id)))
                    ]
                ),
                limit=top_k
            )
            return [hit.payload.get("text", "") for hit in results if hit.payload]
        except Exception as e:
            print(f"[Warning] RAG vector retrieval error: {e}")
            return []
