"""Audiensi ReAct Agent — handles audiensi scheduling conversations.

Uses the OpenAI Responses API with session chaining (previous_response_id)
for efficient multi-turn conversations.
"""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from orchestrator.config import log, cfg
from orchestrator.agent.schemas import AgentAction, AgentContext, AgentResult, ReactLoopResult
from orchestrator.agent.prompts import build_conversation_input_items
from orchestrator.audiensi.prompts import (
    AUDIENSI_SYSTEM_PROMPT,
    build_audiensi_system_prompt,
)
from orchestrator.audiensi.tools import (
    AUDIENSI_TOOL_SCHEMAS,
    AUDIENSI_TOOL_IMPLEMENTATIONS,
    AUDIENSI_TERMINAL_TOOLS,
)
from orchestrator import db

_openai_client: AsyncOpenAI | None = None
_openai_client_key: str = ""


def _get_openai() -> AsyncOpenAI:
    global _openai_client, _openai_client_key
    current_key = cfg.OPENAI_API_KEY
    if _openai_client is None or current_key != _openai_client_key:
        _openai_client = AsyncOpenAI(api_key=current_key)
        _openai_client_key = current_key
    return _openai_client


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


class AudiensiReactAgent:
    """ReAct agent for audiensi scheduling conversations."""

    async def process_incoming_message(
        self, phone: str, message: str, push_name: str = ""
    ) -> AgentResult:
        """Main handler for incoming WA messages in audiensi conversations."""

        # 1. Lookup audiensi conversation
        aud = await db.get_audiensi_conversation_by_phone(phone)
        if not aud:
            log.info("AudiensiReactAgent: no active audiensi for %s", phone)
            return AgentResult(action=AgentAction.ignored)

        aud_id = aud["id"]
        history = json.loads(aud.get("message_history") or "[]")

        # 2. Record incoming message
        await db.add_audiensi_message(aud_id, "contact", message)
        history.append({"role": "contact", "content": message})

        # 3. Set state to ANALYZING
        await db.update_audiensi_state(aud_id, "ANALYZING")

        # 4. Lookup university info
        uni = await db.get_university_by_id(aud["university_id"]) if aud.get("university_id") else None
        uni_name = uni["name"] if uni else ""
        province = uni.get("province") if uni else None
        rector_name = aud.get("rector_name") or (uni.get("rector_name") if uni else None)

        # 5. Get relevant lessons
        situation = "audiensi_followup" if aud.get("attempt_count", 0) > 0 else "audiensi_scheduling"
        lessons = await db.get_lessons_by_situation(situation, province=province)

        # 6. Build context
        context = AgentContext(
            conversation_id=aud_id,
            university_id=aud.get("university_id"),
            university_name=uni_name,
            province=province,
            contact_phone=phone,
            push_name=push_name,
            conversation_history=history,
            current_state=aud["state"],
            attempt_count=aud.get("attempt_count", 0),
            lessons=lessons,
        )

        # 6b. Fetch knowledge base
        knowledge_items = await db.get_knowledge_items("audiensi", active_only=True)

        # 7. Build system prompt (instructions)
        system_prompt = build_audiensi_system_prompt(
            context, lessons,
            rector_name=rector_name,
            contact_role=aud.get("contact_role"),
            custom_instructions=cfg.AUDIENSI_CUSTOM_INSTRUCTIONS or "",
            knowledge_items=knowledge_items,
        )

        # Load previous_response_id for session chaining
        previous_response_id = aud.get("last_response_id")

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
                tools=list(AUDIENSI_TOOL_SCHEMAS),
                context=context,
                previous_response_id=previous_response_id,
            )
        except Exception as e:
            if previous_response_id and "previous_response" in str(e).lower():
                log.warning("Audiensi response ID expired, retrying: %s", e)
                await db.clear_last_response_id("audiensi_conversations", aud_id)
                input_items = build_conversation_input_items(history)
                result = await self._run_react_loop(
                    instructions=system_prompt,
                    input_items=input_items,
                    tools=list(AUDIENSI_TOOL_SCHEMAS),
                    context=context,
                )
            else:
                raise

        response_text = result.response_text
        tool_calls_made = result.tool_calls_made

        # Save response_id for next turn
        if result.last_response_id:
            await db.update_last_response_id("audiensi_conversations", aud_id, result.last_response_id)

        # 8b. Log API call (non-blocking)
        try:
            await db.save_api_call_log({
                "conversation_id": aud_id,
                "chatbot_type": "audiensi",
                "call_type": "reply",
                "situation_tags": [],
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
            log.warning("Failed to save API call log (audiensi): %s", e)

        # 9. Determine state from tool calls
        action, new_state = self._classify_result(tool_calls_made, response_text)

        # 10. Reasoning summary
        reasoning = (
            f"Tools used: {', '.join(tool_calls_made) if tool_calls_made else 'none'}. "
            f"Action: {action.value}."
        )
        await db.update_audiensi_state(aud_id, new_state or aud["state"], agent_reasoning=reasoning)

        # 11. Update state for non-terminal results
        if action == AgentAction.refused and "mark_audiensi_refused" not in tool_calls_made:
            await db.update_audiensi_state(aud_id, "REFUSED")
        elif action == AgentAction.need_more:
            await db.update_audiensi_state(
                aud_id, "NEED_MORE",
                attempt_count=aud.get("attempt_count", 0) + 1,
            )

        # 12. Record bot response
        if response_text:
            await db.add_audiensi_message(aud_id, "bot", response_text)

        return AgentResult(
            action=action,
            response_message=response_text or None,
            conversation_state=new_state,
            tool_calls_made=tool_calls_made,
            reasoning_summary=reasoning,
        )

    async def generate_initial_message(
        self, university_name: str, rector_name: str | None = None,
        contact_name: str | None = None,
    ) -> str:
        """Generate the first audiensi outreach message."""
        client = _get_openai()

        prompt_parts = [
            AUDIENSI_SYSTEM_PROMPT,
            f"\nKONTEKS:\nUniversitas: {university_name}",
        ]
        if rector_name:
            prompt_parts.append(f"Nama Rektor: {rector_name}")
        if contact_name:
            prompt_parts.append(f"Kontak yang dihubungi: {contact_name}")

        # Knowledge base injection
        custom_instr = cfg.AUDIENSI_CUSTOM_INSTRUCTIONS or ""
        if custom_instr.strip():
            prompt_parts.append("\nINSTRUKSI TAMBAHAN DARI OPERATOR:\n" + custom_instr.strip())
        knowledge_items = await db.get_knowledge_items("audiensi", active_only=True)
        if knowledge_items:
            kb_lines = [f"{i}. [{item['title']}] {item['content']}" for i, item in enumerate(knowledge_items, 1)]
            prompt_parts.append("\nBASIS PENGETAHUAN:\n" + "\n".join(kb_lines))

        system_content = "\n".join(prompt_parts)
        response = await client.responses.create(
            model=cfg.AGENT_MODEL,
            instructions=system_content,
            input=(
                "Buat pesan WhatsApp pertama untuk audiensi. "
                "Sebutkan bahwa surat undangan PDF sudah dikirim sebelumnya. "
                "HANYA output pesan WA-nya, tanpa penjelasan."
            ),
            max_output_tokens=cfg.AGENT_MAX_TOKENS,
            temperature=cfg.AGENT_TEMPERATURE,
        )
        response_text = response.output_text

        # Log API call
        try:
            await db.save_api_call_log({
                "chatbot_type": "audiensi",
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
            log.warning("Failed to save API call log (audiensi initial): %s", e)

        return response_text

    async def generate_followup(
        self, audiensi: dict, attempt: int
    ) -> str:
        """Generate a follow-up message for audiensi."""
        client = _get_openai()

        history = json.loads(audiensi.get("message_history") or "[]")
        uni = (
            await db.get_university_by_id(audiensi["university_id"])
            if audiensi.get("university_id") else None
        )

        prompt_parts = [
            AUDIENSI_SYSTEM_PROMPT,
            f"\nIni follow-up ke-{attempt} untuk audiensi.",
        ]

        # Knowledge base injection
        custom_instr = cfg.AUDIENSI_CUSTOM_INSTRUCTIONS or ""
        if custom_instr.strip():
            prompt_parts.append("\nINSTRUKSI TAMBAHAN DARI OPERATOR:\n" + custom_instr.strip())
        knowledge_items = await db.get_knowledge_items("audiensi", active_only=True)
        if knowledge_items:
            kb_lines = [f"{i}. [{item['title']}] {item['content']}" for i, item in enumerate(knowledge_items, 1)]
            prompt_parts.append("\nBASIS PENGETAHUAN:\n" + "\n".join(kb_lines))

        system_content = "\n".join(prompt_parts)
        previous_response_id = audiensi.get("last_response_id")

        followup_instruction = (
            f"Buat pesan follow-up ke-{attempt} untuk audiensi. "
            "Maksimal 1-2 kalimat pendek, natural tapi tetap sopan. "
            "Ingatkan soal surat undangan. HANYA output pesannya."
        )

        if previous_response_id:
            # Chain with existing session
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
                    log.warning("Audiensi followup: response ID expired: %s", e)
                    aud_id = audiensi.get("id")
                    if aud_id:
                        await db.clear_last_response_id("audiensi_conversations", aud_id)
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
        aud_id = audiensi.get("id")
        if aud_id and response.id:
            await db.update_last_response_id("audiensi_conversations", aud_id, response.id)

        # Log API call
        try:
            await db.save_api_call_log({
                "conversation_id": aud_id,
                "chatbot_type": "audiensi",
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
            log.warning("Failed to save API call log (audiensi followup): %s", e)

        return response_text

    async def _run_react_loop(
        self,
        instructions: str,
        input_items: list[dict],
        tools: list[dict],
        context: AgentContext,
        previous_response_id: str | None = None,
    ) -> ReactLoopResult:
        """Core ReAct loop using the Responses API — mirrors ReactAgent pattern."""
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

        # First API call
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
            function_calls = [item for item in response.output if item.type == "function_call"]

            if not function_calls:
                break

            function_outputs: list[dict] = []
            for fc in function_calls:
                name = fc.name
                try:
                    args = json.loads(fc.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_calls_made.append(name)
                log.info("AudiensiReactAgent tool call: %s(%s)", name, args)

                impl = AUDIENSI_TOOL_IMPLEMENTATIONS.get(name)
                if impl is None:
                    result = json.dumps({"error": f"Unknown tool: {name}"})
                else:
                    result = await impl(args, context)

                function_outputs.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result,
                })

                if name in AUDIENSI_TERMINAL_TOOLS:
                    terminal_reached = True

            next_kwargs: dict = {
                "model": cfg.AGENT_MODEL,
                "input": function_outputs,
                "previous_response_id": response.id,
                "temperature": cfg.AGENT_TEMPERATURE,
                "max_output_tokens": cfg.AGENT_MAX_TOKENS,
                "store": True,
            }
            if not terminal_reached and tools:
                next_kwargs["tools"] = tools

            response = await client.responses.create(**next_kwargs)
            _track_usage(response)
            iterations += 1

            if terminal_reached:
                break

        # Max iterations — force final response
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

    _REFUSAL_KEYWORDS = [
        "tidak berminat", "tidak tertarik", "menolak",
        "scam", "penipuan", "penipu",
        "tidak bisa", "gak bisa",
        "jangan hubungi", "stop", "blokir",
    ]

    _BOT_CLOSING_KEYWORDS = [
        "terima kasih atas waktunya",
        "mohon maaf mengganggu",
        "maaf mengganggu",
    ]

    @staticmethod
    def _classify_result(
        tool_calls_made: list[str], response_text: str
    ) -> tuple[AgentAction, str | None]:
        """Determine action from tool calls."""
        if "confirm_schedule" in tool_calls_made:
            return AgentAction.got_number, "SCHEDULED"  # Reuse got_number as "success"
        if "send_zoom_link" in tool_calls_made:
            return AgentAction.got_number, "ZOOM_SENT"
        if "mark_audiensi_refused" in tool_calls_made:
            return AgentAction.refused, "REFUSED"

        # Fallback text analysis
        if response_text:
            text_lower = response_text.lower()
            is_closing = any(kw in text_lower for kw in AudiensiReactAgent._BOT_CLOSING_KEYWORDS)
            is_refusal = any(kw in text_lower for kw in AudiensiReactAgent._REFUSAL_KEYWORDS)
            if is_closing or is_refusal:
                return AgentAction.refused, "REFUSED"

        return AgentAction.need_more, "NEED_MORE"
