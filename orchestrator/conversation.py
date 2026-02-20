"""
Conversation state machine and OpenAI GPT-4o-mini integration
for autonomous WhatsApp outreach.
"""
import json
from datetime import datetime, timezone, timedelta
from enum import Enum

from openai import AsyncOpenAI

from orchestrator.config import log, cfg
from orchestrator.db import (
    validate_phone,
    get_conversation_by_phone,
    update_conversation_state,
    add_message_to_history,
    get_university_by_id,
    update_university_status,
    update_secretariat_phone,
)

_openai_client: AsyncOpenAI | None = None
_openai_client_key: str = ""


def _get_openai() -> AsyncOpenAI:
    global _openai_client, _openai_client_key
    current_key = cfg.OPENAI_API_KEY
    if _openai_client is None or current_key != _openai_client_key:
        _openai_client = AsyncOpenAI(api_key=current_key)
        _openai_client_key = current_key
    return _openai_client


WIB = timezone(timedelta(hours=7))


def get_wib_greeting() -> str:
    hour = datetime.now(WIB).hour
    if hour < 11:
        return "Selamat pagi"
    elif hour < 15:
        return "Selamat siang"
    elif hour < 18:
        return "Selamat sore"
    else:
        return "Selamat malam"


class ConvState(str, Enum):
    PENDING = "PENDING"
    INITIAL_SENT = "INITIAL_SENT"
    WAITING_REPLY = "WAITING_REPLY"
    REPLIED = "REPLIED"
    ANALYZING = "ANALYZING"
    GOT_NUMBER = "GOT_NUMBER"
    NEED_MORE = "NEED_MORE"
    FOLLOWUP_SENT = "FOLLOWUP_SENT"
    REFUSED = "REFUSED"
    NO_REPLY = "NO_REPLY"
    ABANDONED = "ABANDONED"
    UNDELIVERED = "UNDELIVERED"

    @classmethod
    def terminal_states(cls) -> set[str]:
        return {cls.GOT_NUMBER, cls.REFUSED, cls.ABANDONED, cls.UNDELIVERED}


INITIAL_MESSAGE_TEMPLATE = """Selamat pagi,

Izin saya Ali tim dari Asosiasi Artificial Intelligence Indonesia

Kami ingin mengundang Rektor untuk Audiensi Daring Zoom mendiskusikan potensi kolaborasi di {university_name}.

Sebelumnya undangan telah diterima juga oleh Universitas Indonesia, UNAIR, Universitas Pelita Harapan, Binus University dan 120 kampus lainnya

Boleh dibantu no WA pihak yang tepat untuk kami hubungi? Jika ada kontak sekretaris rektor untuk diskusi lanjutan. Terima kasih \U0001f64f\U0001f3fb"""

FOLLOWUP_MESSAGE_TEMPLATE = """Selamat pagi,
Saya Ali dari Asosiasi Artificial Intelligence,
Menindaklanjuti chat sebelumnya izin untuk dapat diskusi mengenai audiensi dengan pihak kampus

Boleh di bantu kontak yg kiranya dapat kami hubungi? Sebelumnya terima kasih \U0001f64f\U0001f3fb"""

SYSTEM_PROMPT_GENERATE = """Kamu adalah Ali dari Asosiasi Artificial Intelligence Indonesia.
Tugasmu adalah membuat pesan WhatsApp pertama untuk mengundang Rektor universitas untuk Audiensi Daring Zoom dan meminta nomor kontak sekretaris rektor.

Aturan:
- Perkenalkan diri sebagai Ali dari Asosiasi Artificial Intelligence Indonesia
- Tujuan: mengundang Rektor untuk Audiensi Daring Zoom mendiskusikan potensi kolaborasi
- Sebutkan bahwa undangan telah diterima oleh UI, UNAIR, UPH, Binus, dan 120 kampus lainnya
- Minta nomor WA pihak yang tepat / sekretaris rektor
- Gunakan bahasa sopan tapi tidak terlalu formal, natural seperti chat WA
- HANYA output pesan WA-nya, tanpa penjelasan lain"""

SYSTEM_PROMPT_ANALYZE = """Kamu adalah Ali dari Asosiasi Artificial Intelligence Indonesia.
Kamu sedang menghubungi narahubung universitas untuk mendapatkan nomor kontak sekretaris rektor / pihak yang tepat untuk audiensi.

Analisis balasan dan tentukan:
1. Apakah mereka memberikan nomor telepon? → action: "got_number"
2. Apakah mereka menolak/tidak bisa membantu? → action: "refused"
3. Apakah mereka meminta info lebih lanjut / belum jelas? → action: "need_followup"
4. Apakah balasannya tidak relevan/tidak jelas? → action: "unclear"

Jawab HANYA dalam format JSON:
{
  "action": "got_number" | "refused" | "need_followup" | "unclear",
  "extracted_number": "08xxxx" atau null,
  "reason": "penjelasan singkat",
  "suggested_response": "balasan yang disarankan" atau null
}"""

SYSTEM_PROMPT_FOLLOWUP = """Kamu adalah Ali dari Asosiasi Artificial Intelligence Indonesia.
Kamu sebelumnya sudah menghubungi narahubung universitas untuk audiensi daring Zoom dengan Rektor, tapi belum dapat balasan.

Aturan:
- Sopan dan tidak memaksa
- Ingatkan kembali tujuan (audiensi dengan pihak kampus, minta kontak yang tepat)
- Natural seperti chat WA biasa
- HANYA output pesan WA-nya"""


class ConversationManager:

    async def generate_initial_message(
        self, university_name: str, contact_name: str | None = None
    ) -> str:
        """Generate the first outreach message, optionally using the agentic system."""
        if cfg.USE_AGENTIC_INITIAL:
            try:
                from orchestrator.agent.react_agent import ReactAgent
                agent = ReactAgent()
                return await agent.generate_initial_message(university_name)
            except Exception as e:
                log.error("Agentic initial message failed, falling back to legacy: %s", e)
        return INITIAL_MESSAGE_TEMPLATE.format(university_name=university_name)

    async def analyze_reply(
        self, conversation_history: list[dict], latest_reply: str,
        push_name: str = "", uni_name: str = "",
    ) -> dict:
        """Analyze incoming reply and decide next action."""
        client = _get_openai()

        context_parts = []
        if push_name:
            context_parts.append(f"Kamu sedang berbicara dengan {push_name}")
        if uni_name:
            context_parts.append(f"dari {uni_name}")
        context_line = ". ".join(context_parts) + ".\n\n" if context_parts else ""
        system_content = context_line + SYSTEM_PROMPT_ANALYZE

        messages = [{"role": "system", "content": system_content}]

        # History compaction: summarize older messages when history is long
        if len(conversation_history) > 10:
            earlier = conversation_history[:-6]
            summary_parts = []
            for m in earlier:
                role_label = "Bot" if m["role"] == "bot" else "Kontak"
                summary_parts.append(f"{role_label}: {m['content'][:80]}")
            summary = "[Ringkasan percakapan sebelumnya: " + "; ".join(summary_parts) + "]"
            messages.append({"role": "user", "content": summary})
            recent = conversation_history[-6:]
        else:
            recent = conversation_history[-6:]

        for msg in recent:
            messages.append({
                "role": "assistant" if msg["role"] == "bot" else "user",
                "content": msg["content"],
            })

        messages.append({
            "role": "user",
            "content": f"Balasan terbaru dari narahubung:\n\n{latest_reply}\n\nAnalisis balasan ini.",
        })

        resp = await client.chat.completions.create(
            model=cfg.AGENT_MODEL,
            messages=messages,
            max_tokens=300,
            temperature=0.1,
        )

        text = resp.choices[0].message.content.strip()

        # Parse JSON response
        try:
            # Find JSON in response
            start = text.index("{")
            end = text.rindex("}") + 1
            result = json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            log.warning(f"Failed to parse GPT analysis: {text}")
            result = {
                "action": "unclear",
                "extracted_number": None,
                "reason": "Failed to parse response",
                "suggested_response": None,
            }

        # Validate extracted number
        if result.get("extracted_number"):
            validated = validate_phone(result["extracted_number"])
            result["extracted_number"] = validated

        return result

    async def generate_followup(
        self, conversation_history: list[dict], attempt_number: int,
        conversation: dict | None = None,
    ) -> str:
        """Generate a follow-up message, optionally using the agentic system."""
        if cfg.USE_AGENTIC_FOLLOWUPS and attempt_number > 1 and conversation:
            try:
                from orchestrator.agent.react_agent import ReactAgent
                agent = ReactAgent()
                return await agent.generate_followup_message(conversation, attempt_number)
            except Exception as e:
                log.error("Agentic followup failed, falling back to legacy: %s", e)
        return await self._generate_followup_legacy(conversation_history, attempt_number)

    async def _generate_followup_legacy(
        self, conversation_history: list[dict], attempt_number: int
    ) -> str:
        """Legacy follow-up generation using fixed template or GPT."""
        if attempt_number <= 1:
            return FOLLOWUP_MESSAGE_TEMPLATE

        client = _get_openai()

        messages = [{"role": "system", "content": SYSTEM_PROMPT_FOLLOWUP}]

        for msg in conversation_history[-4:]:
            messages.append({
                "role": "assistant" if msg["role"] == "bot" else "user",
                "content": msg["content"],
            })

        messages.append({
            "role": "user",
            "content": f"Buat pesan follow-up ke-{attempt_number}. Lebih singkat dan sopan.",
        })

        resp = await client.chat.completions.create(
            model=cfg.AGENT_MODEL,
            messages=messages,
            max_tokens=200,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()

    async def process_incoming_message(
        self, phone: str, message: str, push_name: str = "",
    ) -> dict:
        """
        Main handler for incoming WhatsApp messages.
        Delegates to ReactAgent when cfg.USE_AGENTIC_REPLIES is enabled,
        otherwise falls back to the legacy state-machine approach.
        Returns: {"action": str, "response_message": str|None, "conversation_state": str}
        """
        if cfg.USE_AGENTIC_REPLIES:
            try:
                from orchestrator.agent.react_agent import ReactAgent
                agent = ReactAgent()
                result = await agent.process_incoming_message(phone, message, push_name)
                return {
                    "action": result.action.value,
                    "response_message": result.response_message,
                    "conversation_state": result.conversation_state,
                }
            except Exception as e:
                log.error("Agentic processing failed, falling back to legacy: %s", e)
        return await self._process_incoming_legacy(phone, message, push_name)

    async def _process_incoming_legacy(
        self, phone: str, message: str, push_name: str = "",
    ) -> dict:
        """Legacy handler using the original state-machine approach."""
        conv = await get_conversation_by_phone(phone)
        if not conv:
            log.info(f"Received message from unknown number {phone}, ignoring")
            return {"action": "ignored", "response_message": None, "conversation_state": None}

        conv_id = conv["id"]
        state = conv["state"]
        history = json.loads(conv["message_history"] or "[]")

        # Record incoming message
        await add_message_to_history(conv_id, "contact", message)
        history.append({"role": "contact", "content": message})

        # Update state to analyzing
        await update_conversation_state(conv_id, ConvState.ANALYZING)

        # Lookup university name for AI context
        uni = await get_university_by_id(conv["university_id"]) if conv.get("university_id") else None
        uni_name = uni["name"] if uni else ""

        # Analyze the reply
        analysis = await self.analyze_reply(history, message, push_name=push_name, uni_name=uni_name)
        action = analysis["action"]

        result = {
            "action": action,
            "response_message": None,
            "conversation_state": None,
        }

        if action == "got_number" and analysis.get("extracted_number"):
            # Success! Got the secretariat phone number
            await update_conversation_state(
                conv_id,
                ConvState.GOT_NUMBER,
                extracted_number=analysis["extracted_number"],
            )
            # Update university record
            uni = await get_university_by_id(conv["university_id"])
            if uni:
                await update_secretariat_phone(uni["id"], analysis["extracted_number"])
                await update_university_status(uni["id"], "got_number")

            # Send thank you message
            thank_you = "Terima kasih banyak atas informasinya! Sangat membantu. 🙏"
            result["response_message"] = thank_you
            result["conversation_state"] = ConvState.GOT_NUMBER
            await add_message_to_history(conv_id, "bot", thank_you)

            log.info(f"SUCCESS: Got sekretariat number {analysis['extracted_number']} for university {conv['university_id']}")

            # Auto-queue audiensi conversation
            try:
                from orchestrator.audiensi.auto_queue import create_audiensi_from_success
                import asyncio
                asyncio.create_task(create_audiensi_from_success(conv_id))
            except Exception:
                pass  # Audiensi module may not be available

        elif action == "refused":
            await update_conversation_state(conv_id, ConvState.REFUSED)
            polite_close = "Baik, terima kasih atas waktunya. Mohon maaf mengganggu."
            result["response_message"] = polite_close
            result["conversation_state"] = ConvState.REFUSED
            await add_message_to_history(conv_id, "bot", polite_close)

        elif action in ("need_followup", "unclear"):
            response = analysis.get("suggested_response")
            if not response:
                response = await self._generate_followup_legacy(history, 1)

            await update_conversation_state(
                conv_id,
                ConvState.NEED_MORE,
                attempt_count=conv["attempt_count"] + 1,
            )
            result["response_message"] = response
            result["conversation_state"] = ConvState.NEED_MORE
            await add_message_to_history(conv_id, "bot", response)

        return result


# Singleton
conversation_manager = ConversationManager()
