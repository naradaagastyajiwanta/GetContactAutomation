"""Core ReactAgent class — ReAct loop with tool calling for WhatsApp conversations.

Uses the OpenAI Responses API with session chaining (previous_response_id)
for efficient multi-turn conversations.
"""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from orchestrator.config import log, cfg
from orchestrator.agent.schemas import AgentAction, AgentContext, AgentResult, ReactLoopResult
from orchestrator.agent.prompts import (
    AGENT_BASE_SYSTEM_PROMPT,
    build_agent_system_prompt,
    build_conversation_input_items,
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

        # 6b. Fetch situational knowledge base (keyword matching from DB)
        from orchestrator.agent.situation_detector import detect_situation_tags
        sit_tags = detect_situation_tags(message, conv["state"], conv.get("attempt_count", 0))
        knowledge_items = await db.match_knowledge_items_by_message("agent", message)

        # 7. Build system prompt (instructions)
        system_prompt = build_agent_system_prompt(
            context, lessons,
            custom_instructions=cfg.AGENT_CUSTOM_INSTRUCTIONS or "",
            knowledge_items=knowledge_items,
        )

        # Load previous_response_id for session chaining
        previous_response_id = conv.get("last_response_id")

        # Build input items — only new message if session exists
        if previous_response_id:
            input_items = [{"role": "user", "content": message}]
        else:
            input_items = build_conversation_input_items(history)

        # 8. Run ReAct loop with fallback for expired sessions
        try:
            result = await self._run_react_loop(
                instructions=system_prompt,
                input_items=input_items,
                tools=list(TOOL_SCHEMAS),
                context=context,
                previous_response_id=previous_response_id,
            )
        except Exception as e:
            if previous_response_id and "previous_response" in str(e).lower():
                log.warning("Response ID expired, retrying without session: %s", e)
                await db.clear_last_response_id("conversations", conv_id)
                input_items = build_conversation_input_items(history)
                result = await self._run_react_loop(
                    instructions=system_prompt,
                    input_items=input_items,
                    tools=list(TOOL_SCHEMAS),
                    context=context,
                )
            else:
                raise

        response_text = result.response_text
        tool_calls_made = result.tool_calls_made

        # Save response_id for next turn
        if result.last_response_id:
            await db.update_last_response_id("conversations", conv_id, result.last_response_id)

        # 8b. Log API call (non-blocking)
        try:
            await db.save_api_call_log({
                "conversation_id": conv_id,
                "chatbot_type": "agent",
                "call_type": "reply",
                "situation_tags": sit_tags,
                "knowledge_items_injected": [
                    {"id": ki["id"], "title": ki["title"], "tags": ki.get("situation_tags", "")}
                    for ki in knowledge_items
                ],
                "system_prompt": system_prompt,
                "messages_sent": input_items,
                "model_used": cfg.AGENT_MODEL,
                "tool_calls_made": tool_calls_made,
                "response_text": response_text,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
                "cached_tokens": result.cached_tokens,
            })
        except Exception as e:
            log.warning("Failed to save API call log: %s", e)

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
        """Generate the first outreach message using Responses API with lessons context."""
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
        knowledge_items = await db.get_knowledge_items_by_tags("agent", ["pembuka", "tone_umum"])
        # Also include items matched by trigger_keywords for "pembuka" context
        kw_items = await db.match_knowledge_items_by_message("agent", "pembuka kolaborasi undangan")
        seen_ids = {ki["id"] for ki in knowledge_items}
        for ki in kw_items:
            if ki["id"] not in seen_ids:
                knowledge_items.append(ki)
                seen_ids.add(ki["id"])
        if knowledge_items:
            kb_lines = [f"{i}. [{item['title']}] {item['content']}" for i, item in enumerate(knowledge_items, 1)]
            prompt_parts.append("\nBASIS PENGETAHUAN:\n" + "\n".join(kb_lines))

        system_content = "\n".join(prompt_parts)
        response = await client.responses.create(
            model=cfg.AGENT_MODEL,
            instructions=system_content,
            input="Buat pesan WhatsApp pertama untuk mengundang pihak kampus. HANYA output pesan WA-nya, tanpa penjelasan.",
            max_output_tokens=cfg.AGENT_MAX_TOKENS,
            temperature=cfg.AGENT_TEMPERATURE,
        )
        response_text = response.output_text

        # Log API call
        try:
            await db.save_api_call_log({
                "chatbot_type": "agent",
                "call_type": "initial",
                "situation_tags": ["pembuka", "tone_umum"],
                "knowledge_items_injected": [
                    {"id": ki["id"], "title": ki["title"], "tags": ki.get("situation_tags", "")}
                    for ki in knowledge_items
                ],
                "system_prompt": system_content,
                "model_used": cfg.AGENT_MODEL,
                "response_text": response_text,
                "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                "completion_tokens": response.usage.output_tokens if response.usage else 0,
                "total_tokens": (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
                "cached_tokens": _get_cached_tokens(response),
            })
        except Exception as e:
            log.warning("Failed to save API call log (initial): %s", e)

        return response_text

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
        knowledge_items = await db.get_knowledge_items_by_tags("agent", ["followup", "tone_umum"])
        kw_items = await db.match_knowledge_items_by_message("agent", "followup tindak lanjut")
        seen_ids = {ki["id"] for ki in knowledge_items}
        for ki in kw_items:
            if ki["id"] not in seen_ids:
                knowledge_items.append(ki)
                seen_ids.add(ki["id"])
        if knowledge_items:
            kb_lines = [f"{i}. [{item['title']}] {item['content']}" for i, item in enumerate(knowledge_items, 1)]
            prompt_parts.append("\nBASIS PENGETAHUAN:\n" + "\n".join(kb_lines))

        system_content = "\n".join(prompt_parts)
        previous_response_id = conversation.get("last_response_id")

        followup_instruction = (
            f"Buat pesan follow-up ke-{attempt}. "
            "Maksimal 1-2 kalimat pendek, natural tapi tetap sopan. "
            "HANYA output pesannya."
        )

        if previous_response_id:
            # Chain with existing session — only send new instruction
            try:
                response = await client.responses.create(
                    model=cfg.AGENT_MODEL,
                    instructions=system_content,
                    input=followup_instruction,
                    previous_response_id=previous_response_id,
                    max_output_tokens=cfg.AGENT_MAX_TOKENS,
                    temperature=0.7,
                    store=True,
                )
            except Exception as e:
                if "previous_response" in str(e).lower():
                    log.warning("Followup: response ID expired, sending full context: %s", e)
                    conv_id = conversation.get("id")
                    if conv_id:
                        await db.clear_last_response_id("conversations", conv_id)
                    previous_response_id = None
                else:
                    raise

        if not previous_response_id:
            # No session or expired — send recent history
            input_items: list[dict] = []
            for msg in history[-4:]:
                role = "assistant" if msg.get("role") == "bot" else "user"
                input_items.append({"role": role, "content": msg.get("content", "")})
            input_items.append({"role": "user", "content": followup_instruction})

            response = await client.responses.create(
                model=cfg.AGENT_MODEL,
                instructions=system_content,
                input=input_items,
                max_output_tokens=cfg.AGENT_MAX_TOKENS,
                temperature=0.7,
                store=True,
            )

        response_text = response.output_text

        # Save response_id for future chaining
        conv_id = conversation.get("id")
        if conv_id and response.id:
            await db.update_last_response_id("conversations", conv_id, response.id)

        # Log API call
        try:
            await db.save_api_call_log({
                "conversation_id": conv_id,
                "chatbot_type": "agent",
                "call_type": "followup",
                "situation_tags": ["followup", "tone_umum"],
                "knowledge_items_injected": [
                    {"id": ki["id"], "title": ki["title"], "tags": ki.get("situation_tags", "")}
                    for ki in knowledge_items
                ],
                "system_prompt": system_content,
                "model_used": cfg.AGENT_MODEL,
                "response_text": response_text,
                "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                "completion_tokens": response.usage.output_tokens if response.usage else 0,
                "total_tokens": (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
                "cached_tokens": _get_cached_tokens(response),
            })
        except Exception as e:
            log.warning("Failed to save API call log (followup): %s", e)

        return response_text

    async def _run_react_loop(
        self,
        instructions: str,
        input_items: list[dict],
        tools: list[dict],
        context: AgentContext,
        previous_response_id: str | None = None,
    ) -> ReactLoopResult:
        """Core ReAct loop using the Responses API with session chaining.

        Returns a ReactLoopResult with response text, tool calls, token usage,
        and last_response_id for session chaining.
        """
        client = _get_openai()
        tool_calls_made: list[str] = []
        terminal_reached = False
        iterations = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0

        def _track_usage(resp) -> None:
            nonlocal total_prompt_tokens, total_completion_tokens, total_cached_tokens
            if resp.usage:
                total_prompt_tokens += resp.usage.input_tokens
                total_completion_tokens += resp.usage.output_tokens
                total_cached_tokens += _get_cached_tokens(resp)

        # First API call — includes instructions and full input
        kwargs: dict = {
            "model": cfg.AGENT_MODEL,
            "instructions": instructions,
            "input": input_items,
            "temperature": cfg.AGENT_TEMPERATURE,
            "max_output_tokens": cfg.AGENT_MAX_TOKENS,
            "store": True,
        }
        if tools:
            kwargs["tools"] = tools
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id

        response = await client.responses.create(**kwargs)
        _track_usage(response)

        while iterations < cfg.AGENT_MAX_TOOL_ITERATIONS:
            # Check output for function calls
            function_calls = [item for item in response.output if item.type == "function_call"]

            if not function_calls:
                break

            # Execute tools, build function_call_output items
            function_outputs: list[dict] = []
            for fc in function_calls:
                name = fc.name
                try:
                    args = json.loads(fc.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_calls_made.append(name)
                log.info("ReactAgent tool call: %s(%s)", name, args)

                impl = TOOL_IMPLEMENTATIONS.get(name)
                if impl is None:
                    result = json.dumps({"error": f"Unknown tool: {name}"})
                else:
                    result = await impl(args, context)

                function_outputs.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result,
                })

                if name in TERMINAL_TOOLS:
                    terminal_reached = True

            # Feed results back with previous_response_id chaining
            next_kwargs: dict = {
                "model": cfg.AGENT_MODEL,
                "input": function_outputs,
                "previous_response_id": response.id,
                "temperature": cfg.AGENT_TEMPERATURE,
                "max_output_tokens": cfg.AGENT_MAX_TOKENS,
                "store": True,
            }
            # Remove tools after terminal to force text-only closing response
            if not terminal_reached and tools:
                next_kwargs["tools"] = tools

            response = await client.responses.create(**next_kwargs)
            _track_usage(response)
            iterations += 1

            if terminal_reached:
                break

        # Max iterations reached — force a final text response
        if iterations >= cfg.AGENT_MAX_TOOL_ITERATIONS:
            has_text = any(
                getattr(item, "type", None) == "message"
                for item in response.output
            )
            if not has_text:
                response = await client.responses.create(
                    model=cfg.AGENT_MODEL,
                    input=[{"role": "user", "content": "Berikan respons akhirmu sekarang."}],
                    previous_response_id=response.id,
                    max_output_tokens=cfg.AGENT_MAX_TOKENS,
                    store=True,
                )
                _track_usage(response)

        # Extract response text
        try:
            response_text = response.output_text
        except (ValueError, AttributeError):
            response_text = ""

        return ReactLoopResult(
            response_text=response_text,
            tool_calls_made=tool_calls_made,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
            cached_tokens=total_cached_tokens,
            last_response_id=response.id,
        )

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


def _get_cached_tokens(response) -> int:
    """Safely extract cached_tokens from a Responses API response."""
    try:
        if response.usage and hasattr(response.usage, "input_tokens_details"):
            details = response.usage.input_tokens_details
            if details:
                return getattr(details, "cached_tokens", 0) or 0
    except (AttributeError, TypeError):
        pass
    return 0
