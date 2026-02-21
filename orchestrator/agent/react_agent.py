"""Core ReactAgent class — ReAct loop with tool calling for WhatsApp conversations."""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from orchestrator.config import log, cfg
from orchestrator.agent.schemas import AgentAction, AgentContext, AgentResult
from orchestrator.agent.prompts import (
    AGENT_BASE_SYSTEM_PROMPT,
    build_agent_system_prompt,
    build_conversation_messages,
)
from orchestrator.agent.tools import TOOL_SCHEMAS, TOOL_IMPLEMENTATIONS, TERMINAL_TOOLS
from orchestrator import db

# ---------------------------------------------------------------------------
# Lazy OpenAI client (matches existing pattern in conversation.py)
# ---------------------------------------------------------------------------

_openai_client: AsyncOpenAI | None = None
_openai_client_key: str = ""


def _get_openai() -> AsyncOpenAI:
    global _openai_client, _openai_client_key
    current_key = cfg.OPENAI_API_KEY
    if _openai_client is None or current_key != _openai_client_key:
        _openai_client = AsyncOpenAI(api_key=current_key)
        _openai_client_key = current_key
    return _openai_client


# ---------------------------------------------------------------------------
# ReactAgent
# ---------------------------------------------------------------------------


class ReactAgent:
    """ReAct agent for handling WhatsApp conversations with tool calling."""

    async def process_incoming_message(
        self, phone: str, message: str, push_name: str = ""
    ) -> AgentResult:
        """Main handler for incoming WA messages using ReAct loop."""

        # 1. Lookup conversation
        conv = await db.get_conversation_by_phone(phone)
        if not conv:
            log.info("ReactAgent: message from unknown number %s, ignoring", phone)
            return AgentResult(action=AgentAction.ignored)

        conv_id = conv["id"]
        history = json.loads(conv.get("message_history") or "[]")

        # 2. Record incoming message
        await db.add_message_to_history(conv_id, "contact", message)
        history.append({"role": "contact", "content": message})

        # 3. Set state to ANALYZING
        await db.update_conversation_state(conv_id, "ANALYZING")

        # 4. Lookup university info
        uni = (
            await db.get_university_by_id(conv["university_id"])
            if conv.get("university_id")
            else None
        )
        uni_name = uni["name"] if uni else ""
        province = uni.get("province") if uni else None

        # 5. Get relevant lessons for the current situation
        situation = "followup" if conv.get("attempt_count", 0) > 0 else "initial_contact"
        lessons = await db.get_lessons_by_situation(situation, province=province)

        # 6. Build AgentContext
        context = AgentContext(
            conversation_id=conv_id,
            university_id=conv.get("university_id"),
            university_name=uni_name,
            province=province,
            contact_phone=phone,
            push_name=push_name,
            conversation_history=history,
            current_state=conv["state"],
            attempt_count=conv.get("attempt_count", 0),
            lessons=lessons,
        )

        # 6b. Fetch knowledge base
        knowledge_items = await db.get_knowledge_items("agent", active_only=True)

        # 7. Build prompts
        system_prompt = build_agent_system_prompt(
            context, lessons,
            custom_instructions=cfg.AGENT_CUSTOM_INSTRUCTIONS or "",
            knowledge_items=knowledge_items,
        )
        conv_messages = build_conversation_messages(history)

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(conv_messages)

        # 8. Run ReAct loop
        response_text, tool_calls_made = await self._run_react_loop(
            messages, list(TOOL_SCHEMAS), context
        )

        # 9. Determine final state from tool calls
        action, new_state = self._classify_result(tool_calls_made, response_text)

        # 10. Build reasoning summary
        reasoning = (
            f"Tools used: {', '.join(tool_calls_made) if tool_calls_made else 'none'}. "
            f"Action: {action.value}."
        )
        await db.update_agent_reasoning(conv_id, reasoning)

        # 11. Update conversation state if not already set by a terminal tool
        if action == AgentAction.refused and "mark_conversation_refused" not in tool_calls_made:
            # Fallback refused detected from text — tool wasn't called, so update DB here
            await db.update_conversation_state(conv_id, "REFUSED")
        elif action == AgentAction.need_more:
            await db.update_conversation_state(
                conv_id,
                "NEED_MORE",
                attempt_count=conv.get("attempt_count", 0) + 1,
            )
        elif action == AgentAction.followup:
            await db.update_conversation_state(conv_id, "NEED_MORE")

        # 12. Record bot response in history
        if response_text:
            await db.add_message_to_history(conv_id, "bot", response_text)

        return AgentResult(
            action=action,
            response_message=response_text or None,
            conversation_state=new_state,
            tool_calls_made=tool_calls_made,
            reasoning_summary=reasoning,
        )

    async def generate_initial_message(
        self, university_name: str, province: str | None = None
    ) -> str:
        """Generate the first outreach message using GPT with lessons context."""
        client = _get_openai()

        lessons = await db.get_lessons_by_situation("initial_contact", province=province)

        prompt_parts = [
            AGENT_BASE_SYSTEM_PROMPT,
            f"\nKONTEKS:\nUniversitas: {university_name}",
        ]
        if province:
            prompt_parts.append(f"Provinsi: {province}")

        if lessons:
            lesson_lines = []
            for i, lesson in enumerate(lessons[:3], 1):
                ins = lesson.get("insight", "")
                strat = lesson.get("recommended_strategy", "")
                lesson_lines.append(f"{i}. {ins} -> {strat}")
            prompt_parts.append(
                "\nPELAJARAN:\n" + "\n".join(lesson_lines)
            )

        # Knowledge base injection
        custom_instr = cfg.AGENT_CUSTOM_INSTRUCTIONS or ""
        if custom_instr.strip():
            prompt_parts.append("\nINSTRUKSI TAMBAHAN DARI OPERATOR:\n" + custom_instr.strip())
        knowledge_items = await db.get_knowledge_items("agent", active_only=True)
        if knowledge_items:
            kb_lines = [f"{i}. [{item['title']}] {item['content']}" for i, item in enumerate(knowledge_items, 1)]
            prompt_parts.append("\nBASIS PENGETAHUAN:\n" + "\n".join(kb_lines))

        prompt_parts.append(
            "\nBuat pesan WhatsApp pertama untuk mengundang pihak kampus. "
            "HANYA output pesan WA-nya, tanpa penjelasan."
        )

        resp = await client.chat.completions.create(
            model=cfg.AGENT_MODEL,
            messages=[{"role": "system", "content": "\n".join(prompt_parts)}],
            max_tokens=cfg.AGENT_MAX_TOKENS,
            temperature=cfg.AGENT_TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()

    async def generate_followup_message(
        self, conversation: dict, attempt: int
    ) -> str:
        """Generate a follow-up message with lessons context."""
        client = _get_openai()

        history = json.loads(conversation.get("message_history") or "[]")
        uni = (
            await db.get_university_by_id(conversation["university_id"])
            if conversation.get("university_id")
            else None
        )
        province = uni.get("province") if uni else None

        lessons = await db.get_lessons_by_situation("followup", province=province)

        prompt_parts = [
            AGENT_BASE_SYSTEM_PROMPT,
            f"\nIni percobaan follow-up ke-{attempt}.",
        ]
        if lessons:
            lesson_lines = []
            for i, lesson in enumerate(lessons[:3], 1):
                ins = lesson.get("insight", "")
                strat = lesson.get("recommended_strategy", "")
                lesson_lines.append(f"{i}. {ins} -> {strat}")
            prompt_parts.append(
                "\nPELAJARAN:\n" + "\n".join(lesson_lines)
            )

        # Knowledge base injection
        custom_instr = cfg.AGENT_CUSTOM_INSTRUCTIONS or ""
        if custom_instr.strip():
            prompt_parts.append("\nINSTRUKSI TAMBAHAN DARI OPERATOR:\n" + custom_instr.strip())
        knowledge_items = await db.get_knowledge_items("agent", active_only=True)
        if knowledge_items:
            kb_lines = [f"{i}. [{item['title']}] {item['content']}" for i, item in enumerate(knowledge_items, 1)]
            prompt_parts.append("\nBASIS PENGETAHUAN:\n" + "\n".join(kb_lines))

        messages: list[dict] = [
            {"role": "system", "content": "\n".join(prompt_parts)}
        ]

        # Add recent conversation history
        for msg in history[-4:]:
            role = "assistant" if msg.get("role") == "bot" else "user"
            messages.append({"role": role, "content": msg.get("content", "")})

        messages.append({
            "role": "user",
            "content": f"Buat pesan follow-up ke-{attempt}. Sopan, singkat, dan natural.",
        })

        resp = await client.chat.completions.create(
            model=cfg.AGENT_MODEL,
            messages=messages,
            max_tokens=cfg.AGENT_MAX_TOKENS,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()

    async def _run_react_loop(
        self,
        messages: list[dict],
        tools: list[dict],
        context: AgentContext,
    ) -> tuple[str, list[str]]:
        """Core ReAct loop with tool calling.

        Returns (final_response_text, list_of_tool_names_called).
        """
        client = _get_openai()
        tool_calls_made: list[str] = []
        terminal_reached = False
        iterations = 0

        while iterations < cfg.AGENT_MAX_TOOL_ITERATIONS:
            kwargs: dict = {
                "model": cfg.AGENT_MODEL,
                "messages": messages,
                "temperature": cfg.AGENT_TEMPERATURE,
                "max_tokens": cfg.AGENT_MAX_TOKENS,
            }
            if tools:
                kwargs["tools"] = tools

            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            # If model produced a text-only response (no tool calls), we're done
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                return choice.message.content or "", tool_calls_made

            # Process tool calls
            messages.append(choice.message)  # type: ignore[arg-type]

            for tool_call in choice.message.tool_calls:
                name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_calls_made.append(name)
                log.info("ReactAgent tool call: %s(%s)", name, args)

                impl = TOOL_IMPLEMENTATIONS.get(name)
                if impl is None:
                    result = json.dumps({"error": f"Unknown tool: {name}"})
                else:
                    result = await impl(args, context)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

                if name in TERMINAL_TOOLS:
                    terminal_reached = True

            iterations += 1

            if terminal_reached:
                # One more call without tools to get a closing message
                tools = []

        # Max iterations reached — force a final response
        messages.append({
            "role": "user",
            "content": "Berikan respons akhirmu sekarang.",
        })
        response = await client.chat.completions.create(
            model=cfg.AGENT_MODEL,
            messages=messages,
            max_tokens=cfg.AGENT_MAX_TOKENS,
        )
        return response.choices[0].message.content or "", tool_calls_made

    # Strong refusal indicators — words only the contact (or a closing bot)
    # would use when the conversation is truly over.
    _HARD_REFUSAL_KEYWORDS = [
        "scam", "penipuan", "penipu", "tipu", "bohong",
        "jangan hubungi", "stop", "blokir",
        "salah nomor", "salah sambung",
    ]

    # Bot's own closing phrases that signal it has given up
    _BOT_CLOSING_KEYWORDS = [
        "terima kasih atas waktunya",
        "semoga hari anda",
        "semoga harinya menyenangkan",
        "sukses selalu",
    ]

    @staticmethod
    def _classify_result(
        tool_calls_made: list[str], response_text: str
    ) -> tuple[AgentAction, str | None]:
        """Determine AgentAction and conversation state from tool calls.

        Falls back to text analysis when the model doesn't call a terminal tool
        but the conversation is clearly over (e.g. contact said 'scam').
        Only triggers on strong refusal signals to avoid false positives.
        """
        if "save_extracted_number" in tool_calls_made:
            return AgentAction.got_number, "GOT_NUMBER"
        if "mark_conversation_refused" in tool_calls_made:
            return AgentAction.refused, "REFUSED"

        # Fallback: detect refusal from bot's response text
        # Requires BOTH a closing phrase AND a hard refusal keyword,
        # OR a hard refusal keyword alone — to avoid false positives
        # on polite phrases like "mohon maaf mengganggu".
        if response_text:
            text_lower = response_text.lower()
            has_hard_refusal = any(kw in text_lower for kw in ReactAgent._HARD_REFUSAL_KEYWORDS)
            has_closing = any(kw in text_lower for kw in ReactAgent._BOT_CLOSING_KEYWORDS)

            if has_hard_refusal:
                log.info(
                    "ReactAgent: detected hard refusal keyword in response text, "
                    "overriding to REFUSED"
                )
                return AgentAction.refused, "REFUSED"

            if has_closing and not any(
                tool in tool_calls_made
                for tool in ("lookup_university_info", "get_relevant_lessons",
                             "search_similar_conversations", "check_conversation_history")
            ):
                # Bot wrote a closing phrase AND didn't use any info-gathering tools,
                # meaning it decided to end the conversation on its own
                log.info(
                    "ReactAgent: detected closing phrase without info-gathering, "
                    "overriding to REFUSED"
                )
                return AgentAction.refused, "REFUSED"

        # Default: the agent wants to continue the conversation
        return AgentAction.need_more, "NEED_MORE"
