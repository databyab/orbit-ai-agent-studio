import json
import uuid
from typing import AsyncGenerator, Dict, Any, List, Optional
from groq import AsyncGroq
from openai import AsyncOpenAI
from app.config import get_settings
from app.services.rag import DualStageRAGService
from app.services.tools import SafeToolExecutor
from app.models.entities import Agent, Conversation, Message, Action

settings = get_settings()

class AgentOrchestrator:
    def __init__(self, rag_service: DualStageRAGService, tool_executor: SafeToolExecutor):
        self.rag = rag_service
        self.tool_executor = tool_executor

    def get_llm_client(self, model_name: str):
        if settings.GROQ_API_KEY and (
            model_name.startswith("openai/gpt-oss-")
            or "llama" in model_name.lower()
            or "mixtral" in model_name.lower()
            or "gemma" in model_name.lower()
        ):
            return AsyncGroq(api_key=settings.GROQ_API_KEY), model_name
        elif settings.OPENAI_API_KEY:
            return AsyncOpenAI(api_key=settings.OPENAI_API_KEY), "gpt-4o-mini"
        elif settings.GROQ_API_KEY:
            return AsyncGroq(api_key=settings.GROQ_API_KEY), settings.DEFAULT_MODEL
        else:
            return None, None

    async def execute_turn_stream(
        self,
        agent: Agent,
        conversation: Conversation,
        conversation_messages: List[Message],
        user_message: Optional[str],
        use_knowledge: bool,
        tool_schemas: List[Dict[str, Any]],
        action_map: Dict[str, Action],
        db_session
    ) -> AsyncGenerator[str, None]:
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        text_id = f"txt_{uuid.uuid4().hex[:8]}"

        # 1. Deterministic Q&A Ground Truth Override (Finding FIND-B03)
        if use_knowledge and user_message:
            qna_answer = await self.rag.check_qna_override(str(agent.id), user_message, db_session)
            if qna_answer:
                yield f'data: {json.dumps({"type": "start", "messageId": msg_id})}\n\n'
                yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'
                yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": qna_answer})}\n\n'
                yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'
                yield f'data: {json.dumps({"type": "finish", "finishReason": "stop", "messageMetadata": {"messageId": msg_id, "credits": 1}})}\n\n'
                yield 'data: [DONE]\n\n'

                # Record message to DB
                new_msg = Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=qna_answer,
                    parts=[{"type": "text", "text": qna_answer}]
                )
                db_session.add(new_msg)
                await db_session.commit()
                return

        # 2. Stage 2 Vector Retrieval from Qdrant
        context_chunks = []
        if use_knowledge and user_message:
            context_chunks = await self.rag.retrieve_chunks(str(agent.id), user_message, top_k=4)

        grounding_block = ""
        if context_chunks:
            grounding_block = "\n\n### Grounding Context from Knowledge Base:\n" + "\n---\n".join(context_chunks)

        # 3. System Instructions with Channel Override
        channel = conversation.channel or "widget"
        sys_prompt = agent.instructions
        if agent.channel_instructions and channel in agent.channel_instructions:
            sys_prompt = agent.channel_instructions[channel]

        if use_knowledge:
            full_system_prompt = f"{sys_prompt}{grounding_block}\n\nUse the grounding context for company-specific answers when available. If a specific company detail is not covered, say you don't have that information."
        else:
            full_system_prompt = f"{sys_prompt}\n\nAnswer general questions directly and helpfully. Do not invent company-specific policies, prices, or product details; say when you don't know."

        # 4. Message History Assembly
        messages = [{"role": "system", "content": full_system_prompt}]
        for m in conversation_messages[-8:]: # last 8 turns
            messages.append({"role": m.role, "content": m.content})
        
        if user_message:
            messages.append({"role": "user", "content": user_message})

        # 5. Connect to LLM
        client, model = self.get_llm_client(agent.model)
        if not client:
            err_msg = "No LLM provider key configured. Please set GROQ_API_KEY or OPENAI_API_KEY."
            yield f'data: {json.dumps({"type": "error", "errorText": err_msg})}\n\n'
            yield 'data: [DONE]\n\n'
            return

        yield f'data: {json.dumps({"type": "start", "messageId": msg_id})}\n\n'
        yield f'data: {json.dumps({"type": "text-start", "id": text_id})}\n\n'

        accumulated_text = ""
        accumulated_tool = None

        try:
            llm_stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
                temperature=float(agent.temperature or 0.0),
                stream=True
            )

            async for chunk in llm_stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    accumulated_text += delta.content
                    yield f'data: {json.dumps({"type": "text-delta", "id": text_id, "delta": delta.content})}\n\n'

                if delta.tool_calls:
                    tc = delta.tool_calls[0]
                    if not accumulated_tool:
                        accumulated_tool = {
                            "id": tc.id or f"call_{uuid.uuid4().hex[:8]}",
                            "name": tc.function.name or "",
                            "arguments": tc.function.arguments or ""
                        }
                        yield f'data: {json.dumps({"type": "tool-input-start", "toolCallId": accumulated_tool["id"], "toolName": accumulated_tool["name"]})}\n\n'
                    else:
                        if tc.function.arguments:
                            accumulated_tool["arguments"] += tc.function.arguments
                            yield f'data: {json.dumps({"type": "tool-input-delta", "toolCallId": accumulated_tool["id"], "inputTextDelta": tc.function.arguments})}\n\n'

            yield f'data: {json.dumps({"type": "text-end", "id": text_id})}\n\n'

            if accumulated_tool:
                try:
                    parsed_args = json.loads(accumulated_tool["arguments"])
                except Exception:
                    parsed_args = {}

                action_obj = action_map.get(accumulated_tool["name"])
                
                # Check action type
                if action_obj and action_obj.action_type == "server" and action_obj.url_template:
                    # Execute server action immediately on backend
                    tool_res = await self.tool_executor.execute_server_action(
                        method=action_obj.http_method or "POST",
                        url_template=action_obj.url_template,
                        headers=action_obj.headers or {},
                        body_template=action_obj.body_template,
                        input_args=parsed_args
                    )
                    yield f'data: {json.dumps({"type": "tool-output-available", "toolCallId": accumulated_tool["id"], "output": tool_res})}\n\n'
                    yield f'data: {json.dumps({"type": "finish", "finishReason": "stop", "messageMetadata": {"messageId": msg_id, "credits": 2}})}\n\n'
                else:
                    # Client action or UI widget: emit tool-input-available and suspend turn
                    yield f'data: {json.dumps({"type": "tool-input-available", "toolCallId": accumulated_tool["id"], "toolName": accumulated_tool["name"], "input": parsed_args})}\n\n'
                    yield f'data: {json.dumps({"type": "finish", "finishReason": "tool-calls", "messageMetadata": {"messageId": msg_id, "credits": 1}})}\n\n'

            else:
                yield f'data: {json.dumps({"type": "finish", "finishReason": "stop", "messageMetadata": {"messageId": msg_id, "credits": 1}})}\n\n'

            yield 'data: [DONE]\n\n'

            # Persist message to DB
            parts = [{"type": "text", "text": accumulated_text}]
            if accumulated_tool:
                parts.append({"type": "tool-call", "toolCallId": accumulated_tool["id"], "toolName": accumulated_tool["name"], "input": parsed_args})
            
            new_msg = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=accumulated_text,
                parts=parts
            )
            db_session.add(new_msg)
            await db_session.commit()

        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "errorText": str(e)})}\n\n'
            yield 'data: [DONE]\n\n'
