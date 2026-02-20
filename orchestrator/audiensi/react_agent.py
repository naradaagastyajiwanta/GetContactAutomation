"""Audiensi ReAct Agent — handles audiensi scheduling conversations."""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from orchestrator.config import log, cfg
from orchestrator.agent.schemas import AgentAction, AgentContext, AgentResult
from orchestrator.agent.prompts import build_conversation_messages
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

        # 7. Build prompts
        system_prompt = build_audiensi_system_prompt(
            context, lessons,
            rector_name=rector_name,
            contact_role=aud.get("contact_role"),
        )
        conv_messages = build_conversation_messages(history)

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(conv_messages)

        # 8. Run ReAct loop
        response_text, tool_calls_made = await self._run_react_loop(
            messages, list(AUDIENSI_TOOL_SCHEMAS), context
        )

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

        prompt_parts.append(
            "\nBuat pesan WhatsApp pertama untuk audiensi. "
            "Sebutkan bahwa surat undangan PDF sudah dikirim sebelumnya. "
            "HANYA output pesan WA-nya, tanpa penjelasan."
        )

        resp = await client.chat.completions.create(
            model=cfg.AGENT_MODEL,
            messages=[{"role": "system", "content": "\n".join(prompt_parts)}],
            max_tokens=cfg.AGENT_MAX_TOKENS,
            temperature=cfg.AGENT_TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()

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

        messages: list[dict] = [
            {"role": "system", "content": "\n".join(prompt_parts)}
        ]
        for msg in history[-4:]:
            role = "assistant" if msg.get("role") == "bot" else "user"
            messages.append({"role": role, "content": msg.get("content", "")})

        messages.append({
            "role": "user",
            "content": f"Buat pesan follow-up ke-{attempt} untuk audiensi. Sopan, singkat, ingatkan surat undangan.",
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
        """Core ReAct loop — mirrors the existing ReactAgent pattern."""
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

            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                return choice.message.content or "", tool_calls_made

            messages.append(choice.message)  # type: ignore[arg-type]

            for tool_call in choice.message.tool_calls:
                name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_calls_made.append(name)
                log.info("AudiensiReactAgent tool call: %s(%s)", name, args)

                impl = AUDIENSI_TOOL_IMPLEMENTATIONS.get(name)
                if impl is None:
                    result = json.dumps({"error": f"Unknown tool: {name}"})
                else:
                    result = await impl(args, context)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

                if name in AUDIENSI_TERMINAL_TOOLS:
                    terminal_reached = True

            iterations += 1

            if terminal_reached:
                tools = []

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
