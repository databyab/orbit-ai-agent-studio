import hashlib
import io
import re
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from app.config import get_settings

settings = get_settings()

class IngestionService:
    def __init__(self, qdrant_client: Optional[AsyncQdrantClient] = None):
        self.qdrant = qdrant_client or AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        self.collection_name = settings.QDRANT_COLLECTION
        self._encoder = None

    def get_encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(settings.EMBEDDING_MODEL)
        return self._encoder

    async def ensure_collection(self):
        try:
            collections = await self.qdrant.get_collections()
            names = [c.name for c in collections.collections]
            if self.collection_name not in names:
                await self.qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=settings.EMBEDDING_DIM,
                        distance=qmodels.Distance.COSINE
                    )
                )
                # Create payload index for fast tenant isolation filtering
                await self.qdrant.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="agent_id",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
        except Exception as e:
            print(f"[Warning] Qdrant ensure_collection: {e}")

    def chunk_text(self, text: str, chunk_size: int = 400, overlap: int = 40) -> List[str]:
        words = text.split()
        if not words:
            return []
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk.strip())
        return chunks

    def extract_pdf(self, file_bytes: bytes) -> str:
        reader = PdfReader(io.BytesIO(file_bytes))
        extracted = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted.append(t)
        return "\n".join(extracted)

    def extract_docx(self, file_bytes: bytes) -> str:
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

    async def crawl_url(self, url: str) -> str:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(url, headers={"User-Agent": "ChatbaseReplicaBot/1.0"})
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)

    async def parse_sitemap(self, sitemap_url: str) -> List[str]:
        urls = []
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(sitemap_url)
            soup = BeautifulSoup(resp.text, "xml")
            for loc in soup.find_all("loc"):
                if loc.text:
                    urls.append(loc.text.strip())
        return urls[:50] # bound crawl size for safety

    async def index_content(self, agent_id: str, source_id: str, raw_text: str) -> int:
        chunks = self.chunk_text(raw_text)
        if not chunks:
            return 0

        await self.ensure_collection()
        encoder = self.get_encoder()
        embeddings = encoder.encode(chunks, convert_to_numpy=True).tolist()

        points = []
        for idx, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            point_id = hashlib.sha256(f"{source_id}_{idx}".encode()).hexdigest()[:32]
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "agent_id": str(agent_id),
                        "source_id": str(source_id),
                        "chunk_index": idx,
                        "text": chunk
                    }
                )
            )

        await self.qdrant.upsert(
            collection_name=self.collection_name,
            points=points
        )
        return len(points)

    async def purge_source(self, agent_id: str, source_id: str):
        try:
            await self.qdrant.delete(
                collection_name=self.collection_name,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(key="agent_id", match=qmodels.MatchValue(value=str(agent_id))),
                            qmodels.FieldCondition(key="source_id", match=qmodels.MatchValue(value=str(source_id))),
                        ]
                    )
                )
            )
        except Exception as e:
            print(f"[Warning] Qdrant purge_source failed: {e}")
