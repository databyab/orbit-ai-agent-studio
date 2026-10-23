from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import Procedure, Action, Conversation

class ProcedureEngine:
    """
    Manages workflow state, per-turn arbitration (at most one procedure active per turn),
    and fail-closed channel tool validation.
    """
    async def match_procedure(
        self,
        agent_id: str,
        user_message: str,
        channel: str,
        session: AsyncSession
    ) -> Optional[Procedure]:
        stmt = select(Procedure).where(
            Procedure.agent_id == agent_id,
            Procedure.is_active == True
        )
        res = await session.execute(stmt)
        procedures = res.scalars().all()

        if not procedures or not user_message:
            return None

        clean_msg = user_message.lower()
        # Find highest-affinity procedure trigger
        matched = None
        for proc in procedures:
            trigger_words = [w for w in proc.trigger_description.lower().split() if len(w) > 3]
            if any(w in clean_msg for w in trigger_words):
                matched = proc
                break

        if not matched:
            return None

        # Fail-closed action availability check: verify all actions referenced in graph are enabled on this channel
        graph = matched.steps_graph or {}
        referenced_actions = []
        for node in graph.get("nodes", []):
            action_name = node.get("data", {}).get("action_name")
            if action_name:
                referenced_actions.append(action_name)

        if referenced_actions:
            action_stmt = select(Action).where(
                Action.agent_id == agent_id,
                Action.name.in_(referenced_actions)
            )
            act_res = await session.execute(action_stmt)
            actions_found = {a.name: a for a in act_res.scalars().all()}

            for act_name in referenced_actions:
                act = actions_found.get(act_name)
                if not act or (channel not in act.enabled_channels):
                    # Fail-closed: drop the procedure completely if a referenced tool is unavailable
                    return None

        return matched

    def filter_tool_schemas(
        self,
        available_actions: List[Action],
        active_procedure: Optional[Procedure],
        channel: str
    ) -> List[Dict[str, Any]]:
        """
        Converts actions to OpenAI/Groq function tool definitions.
        Omits 'only_use_in_procedures' actions unless the procedure specifically references them.
        """
        tools = []
        allowed_procedure_tools = set()

        if active_procedure:
            for node in active_procedure.steps_graph.get("nodes", []):
                act_name = node.get("data", {}).get("action_name")
                if act_name:
                    allowed_procedure_tools.add(act_name)

        for action in available_actions:
            if channel not in action.enabled_channels:
                continue

            if action.only_use_in_procedures and action.name not in allowed_procedure_tools:
                # Shielded: do not expose autonomous LLM call for procedure-only action
                continue

            # Build JSON schema
            properties = {}
            required = []
            for param in action.input_parameters:
                p_name = param.get("name")
                p_type = param.get("type", "string")
                properties[p_name] = {
                    "type": p_type,
                    "description": param.get("description", "")
                }
                if param.get("required", True):
                    required.append(p_name)

            tools.append({
                "type": "function",
                "function": {
                    "name": action.name,
                    "description": action.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })

        return tools
