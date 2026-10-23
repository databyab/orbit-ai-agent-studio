from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from datetime import datetime

# --- Agent Schemas ---
class CreateAgentBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: Optional[str] = None
    instructions: Optional[str] = Field(default="You are a helpful customer support agent.", max_length=30000)
    model: Optional[str] = "openai/gpt-oss-120b"
    temp: Optional[float] = Field(default=0.0, ge=0.0, le=1.0)
    visibility: Optional[str] = Field(default="private", pattern="^(public|private)$")

class UpdateAgentBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    instructions: Optional[str] = Field(None, max_length=30000)
    model: Optional[str] = None
    temp: Optional[float] = Field(None, ge=0.0, le=1.0)
    visibility: Optional[str] = None
    allowedDomains: Optional[List[str]] = None
    initialMessages: Optional[List[str]] = None
    suggestedMessages: Optional[List[str]] = None
    channelInstructions: Optional[Dict[str, str]] = None
    ipRateLimits: Optional[Dict[str, Any]] = None
    spamSettings: Optional[Dict[str, Any]] = None

class AgentResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    homepage_url: Optional[str] = None
    instructions: str
    model: str
    temperature: float
    visibility: str
    allowed_domains: List[str]
    initial_messages: List[str]
    suggested_messages: List[str]
    verification_secret: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Source Schemas ---
class CreateSourceText(BaseModel):
    type: str = "text"
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=1048576)

class CreateSourceQnA(BaseModel):
    type: str = "qna"
    name: str = Field(..., min_length=1)
    questions: List[str] = Field(..., min_items=1, max_items=50)
    answer: str = Field(..., min_length=1)

class CreateSourceLink(BaseModel):
    type: str = "link"
    url: str
    linkType: str = Field("individual", pattern="^(individual|sitemap|crawl)$")
    excludePaths: Optional[List[str]] = []
    includeOnlyPaths: Optional[List[str]] = []
    slowScraping: Optional[bool] = False

CreateSourceBody = Union[CreateSourceText, CreateSourceQnA, CreateSourceLink]

class SourceResponse(BaseModel):
    id: UUID
    agent_id: UUID
    name: str
    type: str
    status: str
    error_message: Optional[str] = None
    size_bytes: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Q&A Schemas ---
class QnaItemCreate(BaseModel):
    questions: List[str] = Field(..., min_items=1, max_items=50)
    answer: str = Field(..., min_length=1)

class QnaItemResponse(BaseModel):
    id: UUID
    agent_id: UUID
    questions: List[str]
    answer: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Action (Tool) Schemas ---
class ActionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str
    action_type: str = Field("server", pattern="^(server|client|server_ui|widget_only)$")
    only_use_in_procedures: bool = False
    http_method: Optional[str] = "POST"
    url_template: Optional[str] = None
    headers: Optional[Dict[str, str]] = {}
    input_parameters: Optional[List[Dict[str, Any]]] = []
    body_template: Optional[str] = None
    data_access: Optional[str] = "full"
    enabled_channels: Optional[List[str]] = ["widget", "whatsapp", "slack"]

class ActionResponse(BaseModel):
    id: UUID
    agent_id: UUID
    name: str
    description: str
    action_type: str
    only_use_in_procedures: bool
    http_method: Optional[str] = None
    url_template: Optional[str] = None
    enabled_channels: List[str]
    created_at: datetime

    class Config:
        from_attributes = True

# --- Procedure Schemas ---
class ProcedureCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    trigger_description: str
    is_active: bool = True
    steps_graph: Dict[str, Any] = {"nodes": [], "edges": []}

class ProcedureResponse(BaseModel):
    id: UUID
    agent_id: UUID
    name: str
    trigger_description: str
    is_active: bool
    steps_graph: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True

# --- Chat & Streaming Schemas ---
class ChatRequest(BaseModel):
    message: Optional[str] = None
    conversationId: Optional[UUID] = None
    stream: bool = True
    userId: Optional[str] = Field(None, max_length=128)

class SubmitToolResultRequest(BaseModel):
    toolCallId: str
    output: Any

class MessageFeedbackRequest(BaseModel):
    feedback: str = Field(..., pattern="^(thumbs_up|thumbs_down)$")
    feedbackComment: Optional[str] = None

class MessagePart(BaseModel):
    type: str # 'text', 'tool-call', 'tool-result'
    text: Optional[str] = None
    toolCallId: Optional[str] = None
    toolName: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Any] = None

class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    parts: List[Dict[str, Any]]
    feedback: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    id: UUID
    agent_id: UUID
    user_id: Optional[str] = None
    channel: str
    status: str
    created_at: datetime
    messages: Optional[List[MessageResponse]] = []

    class Config:
        from_attributes = True
