import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, Numeric, Boolean, BigInteger,
    ForeignKey, DateTime, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    plan_tier = Column(String(20), nullable=False, default="standard")
    credit_balance = Column(Integer, nullable=False, default=1000)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    agents = relationship("Agent", back_populates="workspace", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="workspace", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(12), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="api_keys")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    homepage_url = Column(Text, nullable=True)
    instructions = Column(Text, nullable=False, default="You are a helpful customer support agent.")
    model = Column(String(50), nullable=False, default="openai/gpt-oss-120b")
    temperature = Column(Numeric(3, 2), nullable=False, default=0.0)
    visibility = Column(String(10), nullable=False, default="private")
    allowed_domains = Column(ARRAY(Text), default=[])
    initial_messages = Column(ARRAY(Text), default=["Hello! How can I help you today?"])
    suggested_messages = Column(ARRAY(Text), default=[])
    channel_instructions = Column(JSONB, default={})
    ip_rate_limits = Column(JSONB, default={"max_requests": 30, "window_seconds": 60})
    spam_settings = Column(JSONB, default={"enabled": True, "block_repeated_messages": True})
    verification_secret = Column(String(64), nullable=False, default=lambda: uuid.uuid4().hex)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="agents")
    sources = relationship("Source", back_populates="agent", cascade="all, delete-orphan")
    qna_items = relationship("QnaItem", back_populates="agent", cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="agent", cascade="all, delete-orphan")
    procedures = relationship("Procedure", back_populates="agent", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="agent", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False) # 'text', 'file', 'link', 'qna', 'notion'
    status = Column(String(20), nullable=False, default="Syncing") # 'Syncing', 'Synced', 'Failed'
    error_message = Column(Text, nullable=True)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    config = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    agent = relationship("Agent", back_populates="sources")
    qna_items = relationship("QnaItem", back_populates="source", cascade="all, delete-orphan")


class QnaItem(Base):
    __tablename__ = "qna_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=True)
    questions = Column(ARRAY(Text), nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    agent = relationship("Agent", back_populates="qna_items")
    source = relationship("Source", back_populates="qna_items")


class Action(Base):
    __tablename__ = "actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    action_type = Column(String(20), nullable=False, default="server") # 'server', 'client', 'server_ui', 'widget_only'
    only_use_in_procedures = Column(Boolean, nullable=False, default=False)
    http_method = Column(String(10), default="POST")
    url_template = Column(Text, nullable=True)
    headers = Column(JSONB, default={})
    input_parameters = Column(JSONB, nullable=False, default=[])
    body_template = Column(Text, nullable=True)
    data_access = Column(String(10), nullable=False, default="full")
    enabled_channels = Column(ARRAY(Text), default=["widget", "whatsapp", "slack"])
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    agent = relationship("Agent", back_populates="actions")


class Procedure(Base):
    __tablename__ = "procedures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    trigger_description = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    steps_graph = Column(JSONB, nullable=False, default={"nodes": [], "edges": []})
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    agent = relationship("Agent", back_populates="procedures")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(128), nullable=True, index=True)
    channel = Column(String(20), nullable=False, default="widget")
    status = Column(String(20), nullable=False, default="active") # 'active', 'escalated', 'closed'
    active_procedure_id = Column(UUID(as_uuid=True), ForeignKey("procedures.id", ondelete="SET NULL"), nullable=True)
    active_procedure_step = Column(String(50), nullable=True)
    metadata_ = Column("metadata", JSONB, default={})
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    agent = relationship("Agent", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(15), nullable=False) # 'user', 'assistant', 'system', 'tool'
    content = Column(Text, nullable=False, default="")
    parts = Column(JSONB, nullable=False, default=[]) # MessageParts list
    tool_call_id = Column(String(64), nullable=True)
    feedback = Column(String(15), nullable=True) # 'thumbs_up', 'thumbs_down'
    feedback_comment = Column(Text, nullable=True)
    credits_consumed = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    conversation = relationship("Conversation", back_populates="messages")
